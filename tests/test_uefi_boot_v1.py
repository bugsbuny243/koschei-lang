"""Tests for Koschei x86-64 UEFI bare-metal kernel, GDT/IDT, Titan PMM, W^X CR3, PIC/PIT/TSC & Shell v5."""
from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei import cli as _cli
from koschei.cli_entry import main as cli_main
from koschei.mir import require_mir
from koschei.modules import check_graph
from koschei.uefi_boot_v1 import (
    COM1_DLL,
    COM1_DLM,
    COM1_FCR,
    COM1_IER,
    COM1_LCR,
    COM1_MCR,
    GDT_KERNEL_CODE64_DESC,
    GDT_KERNEL_DATA64_DESC,
    GDT_NULL_DESC,
    IMAGE_SUBSYSTEM_EFI_APPLICATION,
    KERNEL_V3_BANNER,
    KERNEL_V4_BANNER,
    KERNEL_V5_BANNER,
    MORTH_TRAP_BANNER,
    PE32PLUS_MACHINE_X86_64,
    PE32PLUS_MAGIC,
    PIT_1000HZ_DIVISOR,
    POST_EBS_BANNER,
    PTE_NX,
    PTE_PRESENT,
    PTE_RW,
    SHELL_EPOCH_REPLY,
    SHELL_HALT_REPLY,
    SHELL_MEM_REPLY,
    SHELL_STATUS_REPLY,
    UART_RX_PREFIX,
    UartPortWrite,
    UefiBootError,
    build_fat16_esp_image_v1,
    build_uefi_pe32plus_v1,
    simulate_uefi_x86_64_serial_v1,
)


class UefiBareMetalBootV1Tests(unittest.TestCase):
    def _compile_source(
        self,
        source_code: str,
        *,
        include_banner: bool = True,
        halt_mode: str = "return",
        exit_boot_services: bool = True,
        enable_serial_rx: bool = True,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            ks_path = Path(tmp) / "main.ks"
            ks_path.write_text(source_code, encoding="utf-8")
            graph = _cli.open_graph(str(ks_path))
            check_graph(graph)
            mir = require_mir(graph)
            return build_uefi_pe32plus_v1(
                mir,
                include_banner=include_banner,
                halt_mode=halt_mode,
                exit_boot_services=exit_boot_services,
                enable_serial_rx=enable_serial_rx,
            )

    def test_pe32plus_header_and_sections_are_valid_x86_64_efi_application(self) -> None:
        artifact = self._compile_source('fn main() { println("HELLO-UEFI") }')
        efi = artifact.efi_bytes

        self.assertEqual(efi[0:2], b"MZ")
        pe_off = struct.unpack_from("<I", efi, 0x3C)[0]
        self.assertEqual(efi[pe_off : pe_off + 4], b"PE\x00\x00")

        machine, num_sections = struct.unpack_from("<HH", efi, pe_off + 4)
        self.assertEqual(machine, PE32PLUS_MACHINE_X86_64)
        self.assertEqual(num_sections, 2)

        opt_off = pe_off + 24
        magic = struct.unpack_from("<H", efi, opt_off)[0]
        subsystem = struct.unpack_from("<H", efi, opt_off + 68)[0]
        self.assertEqual(magic, PE32PLUS_MAGIC)
        self.assertEqual(subsystem, IMAGE_SUBSYSTEM_EFI_APPLICATION)

    def test_uart_16550_com1_initialization_and_serial_stream_match_mir(self) -> None:
        artifact = self._compile_source(
            'fn main() {\n    println("LINE-1")\n    println("LINE-2")\n}\n',
            include_banner=False,
            exit_boot_services=False,
            enable_serial_rx=False,
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes)

        self.assertEqual(emulated.exit_status, 0)
        self.assertEqual(
            emulated.uart_init_writes,
            (
                UartPortWrite(COM1_IER, 0x00),
                UartPortWrite(COM1_LCR, 0x80),
                UartPortWrite(COM1_DLL, 0x01),
                UartPortWrite(COM1_DLM, 0x00),
                UartPortWrite(COM1_LCR, 0x03),
                UartPortWrite(COM1_FCR, 0xC7),
                UartPortWrite(COM1_MCR, 0x0B),
            ),
        )
        self.assertEqual(emulated.serial_bytes, b"LINE-1\r\nLINE-2\r\n")
        self.assertEqual(emulated.conout_text, "LINE-1\r\nLINE-2\r\n")

    def test_gdt_idt_titan_pmm_wx_cr3_pic_pit_tsc_and_shell_commands(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("KERNEL-HANDOVER") }',
            include_banner=False,
            exit_boot_services=True,
            enable_serial_rx=True,
        )

        # 1. Test STATUS shell command
        emulated = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"STATUS\n",
        )
        self.assertEqual(emulated.exit_status, 0)
        self.assertTrue(emulated.memory_map_acquired)
        self.assertTrue(emulated.exit_boot_services_called)
        self.assertTrue(emulated.boot_services_tombstoned)
        self.assertTrue(emulated.gdt_loaded)
        self.assertEqual(
            emulated.gdt_entries,
            (GDT_NULL_DESC, GDT_KERNEL_CODE64_DESC, GDT_KERNEL_DATA64_DESC),
        )
        self.assertTrue(emulated.idt_loaded)
        self.assertEqual(emulated.idt_gate_count, 32)
        self.assertEqual(emulated.titan_total_usable_pages, 32768)
        self.assertEqual(emulated.titan_allocated_page_phys, 0x00100000)
        self.assertEqual(emulated.titan_remaining_pages, 32764)

        # Verify 4-level W^X page tables loaded into CR3
        self.assertEqual(emulated.cr3_pml4_phys, 0x00100000)
        self.assertTrue(emulated.wx_enforced)
        self.assertTrue(bool(emulated.text_pte_flags & PTE_PRESENT))
        self.assertFalse(bool(emulated.text_pte_flags & PTE_RW))
        self.assertFalse(bool(emulated.text_pte_flags & PTE_NX))
        self.assertTrue(bool(emulated.rdata_pte_flags & PTE_PRESENT))
        self.assertFalse(bool(emulated.rdata_pte_flags & PTE_RW))
        self.assertTrue(bool(emulated.rdata_pte_flags & PTE_NX))

        # Verify 8259 PIC remap/mask, 8254 PIT 1000Hz divisor, and TSC anchor at epoch 2
        self.assertTrue(emulated.pic_remapped_and_masked)
        self.assertEqual(emulated.pit_divisor, PIT_1000HZ_DIVISOR)
        self.assertGreater(emulated.tsc_genesis, 0)
        self.assertEqual(emulated.active_epoch, 2)
        self.assertIn(SHELL_STATUS_REPLY, emulated.serial_bytes)

        # 2. Test EPOCH shell command (Vormir/Hela epoch advance 2 -> 3 with monotonic rdtsc)
        emulated_epoch = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"EPOCH\n",
        )
        self.assertEqual(emulated_epoch.active_epoch, 3)
        self.assertGreater(emulated_epoch.tsc_latest, emulated_epoch.tsc_genesis)
        self.assertIn(SHELL_EPOCH_REPLY, emulated_epoch.serial_bytes)

        # 3. Test MEM shell command
        emulated_mem = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"MEM\n",
        )
        self.assertIn(SHELL_MEM_REPLY, emulated_mem.serial_bytes)

        # 4. Test MIR shell command
        emulated_mir = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"MIR\n",
        )
        self.assertIn(
            f"[KOSCHEI-SHELL] sealed_mir_sha256={artifact.mir_fingerprint}\r\n".encode("utf-8"),
            emulated_mir.serial_bytes,
        )

        # 5. Test HALT shell command
        emulated_halt = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"HALT\n",
        )
        self.assertIn(SHELL_HALT_REPLY, emulated_halt.serial_bytes)

    def test_idt_cpu_exception_routes_to_morth_fail_closed_serial_trap(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("TRAP-TEST") }',
            include_banner=False,
            exit_boot_services=True,
            enable_serial_rx=True,
        )
        emulated = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            trigger_exception_vector=14,
        )
        self.assertTrue(emulated.exception_trapped)
        self.assertIn(MORTH_TRAP_BANNER, emulated.serial_bytes)

    def test_halt_mode_executes_cli_hlt_after_flushing_serial(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("HALT-TEST") }',
            include_banner=False,
            halt_mode="halt",
            exit_boot_services=True,
            enable_serial_rx=False,
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes)
        self.assertTrue(emulated.exit_boot_services_called)
        self.assertTrue(emulated.gdt_loaded)
        self.assertTrue(emulated.idt_loaded)
        self.assertTrue(emulated.wx_enforced)
        self.assertTrue(emulated.pic_remapped_and_masked)
        self.assertEqual(
            emulated.serial_bytes,
            b"HALT-TEST\r\n"
            + POST_EBS_BANNER
            + KERNEL_V3_BANNER
            + KERNEL_V4_BANNER
            + KERNEL_V5_BANNER,
        )
        self.assertEqual(emulated.conout_text, "HALT-TEST\r\n")

    def test_host_os_capabilities_are_rejected_fail_closed_on_bare_metal(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let d = caps.disk.allow("/tmp")
    let content = d.read("/tmp/a.txt") or return
    println(content)
}
"""
        with self.assertRaises(UefiBootError) as ctx:
            self._compile_source(source)
        self.assertEqual(ctx.exception.code, "KS4010")
        self.assertIn("forbids host OS capabilities", ctx.exception.message)

    def test_reproducible_efi_and_fat16_esp_image_generation(self) -> None:
        a1 = self._compile_source('fn main() { println("DETERMINISTIC") }')
        a2 = self._compile_source('fn main() { println("DETERMINISTIC") }')
        self.assertEqual(a1.efi_bytes, a2.efi_bytes)
        self.assertEqual(a1.efi_sha256, a2.efi_sha256)

        img = build_fat16_esp_image_v1(a1)
        self.assertEqual(len(img), 4 * 1024 * 1024)
        self.assertEqual(img[510:512], b"\x55\xAA")
        self.assertIn(b"KOSCHEI_ESP", img[:512])
        self.assertIn(b"BOOTX64 EFI", img)
        self.assertIn(a1.efi_bytes, img)

    def test_example_uefi_boot_program_and_cli_json_workflow(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        example_ks = repo_root / "examples" / "uefi_boot" / "boot.ks"
        self.assertTrue(example_ks.is_file())

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            efi_out = tmp_path / "BOOTX64.EFI"
            esp_dir = tmp_path / "esp"
            esp_img = tmp_path / "esp.img"
            asm_out = tmp_path / "boot.s"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cli_main(
                    [
                        "uefi-boot",
                        str(example_ks),
                        "-o",
                        str(efi_out),
                        "--esp-dir",
                        str(esp_dir),
                        "--esp-image",
                        str(esp_img),
                        "--emit-asm",
                        str(asm_out),
                        "--rx-input",
                        "EPOCH",
                        "--verify-emulate",
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["subsystem"], 10)
            self.assertTrue(summary["verified_emulation"])
            self.assertTrue(summary["memory_map_acquired"])
            self.assertTrue(summary["exit_boot_services_called"])
            self.assertTrue(summary["boot_services_tombstoned"])
            self.assertTrue(summary["gdt_loaded"])
            self.assertTrue(summary["idt_loaded"])
            self.assertEqual(summary["idt_gate_count"], 32)
            self.assertEqual(summary["titan_total_usable_pages"], 32768)
            self.assertEqual(summary["titan_allocated_page_phys"], 0x100000)
            self.assertEqual(summary["titan_remaining_pages"], 32764)
            self.assertEqual(summary["cr3_pml4_phys"], 0x100000)
            self.assertTrue(summary["wx_enforced"])
            self.assertTrue(summary["pic_remapped_and_masked"])
            self.assertEqual(summary["pit_divisor"], PIT_1000HZ_DIVISOR)
            self.assertEqual(summary["active_epoch"], 3)

            if shutil.which("objdump"):
                proc = subprocess.run(
                    ["objdump", "-f", "-h", "-d", "-M", "intel", str(efi_out)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("pei-x86-64", proc.stdout)
                self.assertIn("lgdt", proc.stdout)
                self.assertIn("lidt", proc.stdout)
                self.assertIn("mov    cr3,rax", proc.stdout)
                self.assertIn("rdtsc", proc.stdout)


if __name__ == "__main__":
    unittest.main()
