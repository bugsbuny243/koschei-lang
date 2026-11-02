"""Tests for the Koschei x86-64 UEFI boot prototype v5 under the built-in emulator.

The emulator models what real QEMU/OVMF runs showed (``test_uefi_boot_qemu_v1``
boots the same images there): OVMF's memory-map size, a map key that can go
stale, and a page-table switch that faults when the new tables leave the
running code, the stack or the IDT unmapped.
"""
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
    EFI_BUFFER_TOO_SMALL,
    EXPERIMENTAL_CR3_BANNER,
    MEMORY_MAP_BUFFER_BYTES,
    OVMF_MEASURED_DESCRIPTOR_COUNT,
    SHELL_READY_BANNER,
    SHELL_TRAP_REPLY,
    SHELL_UNKNOWN_REPLY,
    expected_serial_v1,
    hex_field,
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
        experimental_page_tables: bool = False,
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
                experimental_page_tables=experimental_page_tables,
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

    def test_exit_boot_services_gdt_idt_pic_pit_tsc_and_shell_commands(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("KERNEL-HANDOVER") }',
            include_banner=False,
            exit_boot_services=True,
            enable_serial_rx=True,
        )

        # 1. STATUS: the boot report prints exactly the values the run read.
        emulated = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"STATUS\n",
        )
        self.assertEqual(emulated.exit_status, 0)
        self.assertTrue(emulated.waiting_for_input)
        self.assertTrue(emulated.memory_map_acquired)
        self.assertTrue(emulated.exit_boot_services_called)
        self.assertTrue(emulated.boot_services_tombstoned)
        self.assertEqual(emulated.exit_boot_services_attempts, 1)
        self.assertEqual(emulated.memory_map_bytes, OVMF_MEASURED_DESCRIPTOR_COUNT * 48)
        self.assertEqual(emulated.descriptor_bytes, 48)
        self.assertTrue(emulated.gdt_loaded)
        self.assertEqual(
            emulated.gdt_entries,
            (GDT_NULL_DESC, GDT_KERNEL_CODE64_DESC, GDT_KERNEL_DATA64_DESC),
        )
        self.assertEqual(emulated.code_segment_selector, 0x08)
        self.assertEqual(emulated.data_segment_selector, 0x10)
        self.assertTrue(emulated.idt_loaded)
        self.assertEqual(emulated.idt_gate_count, 32)
        self.assertEqual(emulated.image_text_address, 0x140001000)

        # No page-table switch without the experimental flag.
        self.assertEqual(emulated.cr3_pml4_phys, 0)
        self.assertFalse(emulated.wx_enforced)

        # 8259 PIC remap/mask, 8254 PIT divisor, TSC sample at epoch 2
        self.assertTrue(emulated.pic_remapped_and_masked)
        self.assertEqual(emulated.pit_divisor, PIT_1000HZ_DIVISOR)
        self.assertGreater(emulated.tsc_genesis, 0)
        self.assertEqual(emulated.active_epoch, 2)
        self.assertEqual(emulated.serial_bytes, expected_serial_v1(artifact, emulated, command="STATUS"))
        self.assertIn(SHELL_STATUS_REPLY + hex_field(2), emulated.serial_bytes)

        # 2. EPOCH advances 2 -> 3 and prints the new TSC sample.
        emulated_epoch = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"EPOCH\n",
        )
        self.assertEqual(emulated_epoch.active_epoch, 3)
        self.assertGreater(emulated_epoch.tsc_latest, emulated_epoch.tsc_genesis)
        self.assertEqual(
            emulated_epoch.serial_bytes, expected_serial_v1(artifact, emulated_epoch, command="EPOCH")
        )

        # 3. MEM reports the firmware's map, not an invented allocator.
        emulated_mem = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"MEM\n",
        )
        self.assertIn(SHELL_MEM_REPLY + hex_field(emulated_mem.memory_map_bytes), emulated_mem.serial_bytes)
        self.assertEqual(emulated_mem.serial_bytes, expected_serial_v1(artifact, emulated_mem, command="MEM"))

        # 4. MIR
        emulated_mir = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"MIR\n",
        )
        self.assertIn(
            f"[KOSCHEI-SHELL] sealed_mir_sha256={artifact.mir_fingerprint}\r\n".encode("utf-8"),
            emulated_mir.serial_bytes,
        )

        # 5. HALT ends the shell; an unknown line gets help and the shell goes on.
        emulated_halt = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"FOO\nHALT\n",
        )
        self.assertIn(SHELL_UNKNOWN_REPLY, emulated_halt.serial_bytes)
        self.assertTrue(emulated_halt.serial_bytes.endswith(SHELL_HALT_REPLY))
        self.assertFalse(emulated_halt.waiting_for_input)

        # 6. TRAP executes ud2; #UD reaches the fail-closed handler through the IDT.
        emulated_trap = simulate_uefi_x86_64_serial_v1(
            artifact.efi_bytes,
            rx_input=b"TRAP\n",
        )
        self.assertTrue(emulated_trap.exception_trapped)
        self.assertTrue(emulated_trap.serial_bytes.endswith(SHELL_TRAP_REPLY + MORTH_TRAP_BANNER))

    def test_memory_map_buffer_holds_the_map_ovmf_reports(self) -> None:
        # OVMF reported 0x17d0 bytes on QEMU q35; the old 4 KiB buffer was too
        # small, so GetMemoryMap failed and the boot never left the firmware.
        self.assertGreater(OVMF_MEASURED_DESCRIPTOR_COUNT * 48, 4096)
        self.assertGreaterEqual(MEMORY_MAP_BUFFER_BYTES, 4 * OVMF_MEASURED_DESCRIPTOR_COUNT * 48)

    def test_a_map_too_large_for_the_buffer_returns_the_firmware_status(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("BIG-MAP") }', include_banner=False, enable_serial_rx=False
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes, memory_descriptor_count=1000)
        self.assertEqual(emulated.exit_status, EFI_BUFFER_TOO_SMALL)
        self.assertFalse(emulated.exit_boot_services_called)
        self.assertEqual(emulated.exit_boot_services_calls, 0)
        self.assertEqual(emulated.memory_map_bytes, 1000 * 48)
        self.assertEqual(emulated.serial_bytes, expected_serial_v1(artifact, emulated))
        self.assertIn(b"FAILED: GetMemoryMap status=0x8000000000000005", emulated.serial_bytes)

    def test_a_stale_map_key_is_retried_once_with_a_fresh_map(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("STALE") }', include_banner=False, enable_serial_rx=False
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes, stale_map_key_once=True)
        self.assertTrue(emulated.exit_boot_services_called)
        self.assertEqual(emulated.exit_boot_services_calls, 2)
        self.assertEqual(emulated.exit_boot_services_attempts, 2)
        self.assertEqual(emulated.serial_bytes, expected_serial_v1(artifact, emulated))

    def test_experimental_page_tables_fault_and_print_no_success(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("CR3") }', include_banner=False, experimental_page_tables=True
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes)
        self.assertTrue(emulated.triple_fault)
        self.assertFalse(emulated.wx_enforced)
        self.assertNotEqual(emulated.cr3_pml4_phys, 0)
        self.assertNotIn(EXPERIMENTAL_CR3_BANNER, emulated.serial_bytes)
        self.assertNotIn(KERNEL_V5_BANNER, emulated.serial_bytes)
        self.assertEqual(emulated.serial_bytes, expected_serial_v1(artifact, emulated))
        default = self._compile_source('fn main() { println("CR3") }', include_banner=False)
        self.assertNotIn(b"\x0f\x22\xd8", default.efi_bytes)  # no mov cr3 unless asked

    def test_the_shell_and_page_tables_need_exit_boot_services(self) -> None:
        for options in ({"enable_serial_rx": True}, {"enable_serial_rx": False, "experimental_page_tables": True}):
            with self.subTest(options=options), self.assertRaises(UefiBootError) as raised:
                self._compile_source('fn main() { println("X") }', exit_boot_services=False, **options)
            self.assertEqual(raised.exception.code, "KS4010")

    def test_the_mir_footer_claims_no_boot_result(self) -> None:
        artifact = self._compile_source('fn main() { println("FOOTER") }')
        self.assertIn(b"[KOSCHEI-UEFI-V1] sealed MIR output complete\r\n", artifact.serial_payload)
        self.assertNotIn(b"EFI_SUCCESS", artifact.serial_payload)

    def test_the_assembly_listing_is_the_image_bytes(self) -> None:
        artifact = self._compile_source('fn main() { println("LISTING") }')
        efi = artifact.efi_bytes
        pe_off = struct.unpack_from("<I", efi, 0x3C)[0]
        opt_size = struct.unpack_from("<H", efi, pe_off + 20)[0]
        sections = pe_off + 24 + opt_size
        listed = {}
        for name in (".text", ".rdata"):
            block = artifact.assembly_source.split(f".section {name}")[1].split(".section")[0]
            listed[name] = bytes(int(value, 16) for value in __import__("re").findall(r"0x([0-9a-f]{2})", block))
        for index, name in enumerate((".text", ".rdata")):
            vsize, _, _, raw_ptr = struct.unpack_from("<IIII", efi, sections + index * 40 + 8)
            with self.subTest(section=name):
                self.assertEqual(listed[name], efi[raw_ptr : raw_ptr + vsize])

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
        self.assertFalse(emulated.wx_enforced)  # paging stays the firmware's
        self.assertTrue(emulated.pic_remapped_and_masked)
        self.assertFalse(emulated.waiting_for_input)
        self.assertEqual(emulated.serial_bytes, expected_serial_v1(artifact, emulated))
        self.assertTrue(emulated.serial_bytes.startswith(b"HALT-TEST\r\n" + POST_EBS_BANNER))
        self.assertIn(KERNEL_V3_BANNER, emulated.serial_bytes)
        self.assertIn(KERNEL_V4_BANNER, emulated.serial_bytes)
        self.assertIn(KERNEL_V5_BANNER, emulated.serial_bytes)
        self.assertEqual(emulated.conout_text, "HALT-TEST\r\n")

    def test_after_exit_boot_services_the_image_halts_even_in_return_mode(self) -> None:
        artifact = self._compile_source(
            'fn main() { println("NO-RETURN") }',
            include_banner=False,
            halt_mode="return",
            enable_serial_rx=False,
        )
        emulated = simulate_uefi_x86_64_serial_v1(artifact.efi_bytes)
        self.assertTrue(emulated.exit_boot_services_called)
        self.assertEqual(emulated.exit_status, 0)
        self.assertTrue(artifact.efi_bytes.count(b"\xFA\xF4\xEB\xFD") >= 1)

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
        self.assertEqual(img, build_fat16_esp_image_v1(a2))

        # The FAT type follows the cluster count alone; under 4085 it is FAT12,
        # which OVMF could not read as this volume's FAT16.
        bytes_per_sector, sectors_per_cluster, reserved = struct.unpack_from("<HBH", img, 11)
        fats, root_entries, total = img[16], *struct.unpack_from("<HH", img, 17)
        sectors_per_fat = struct.unpack_from("<H", img, 22)[0]
        root_sectors = root_entries * 32 // bytes_per_sector
        clusters = (total - reserved - fats * sectors_per_fat - root_sectors) // sectors_per_cluster
        self.assertGreaterEqual(clusters, 4085)
        self.assertLess(clusters, 65525)
        if shutil.which("fsck.fat"):
            with tempfile.TemporaryDirectory() as tmp:
                image_path = Path(tmp) / "esp.img"
                image_path.write_bytes(img)
                checked = subprocess.run(
                    ["fsck.fat", "-n", "-v", str(image_path)], capture_output=True, text=True, check=False
                )
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                self.assertIn("16 bit entries", checked.stdout)

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
            self.assertEqual(summary["code_segment_selector"], 0x08)
            self.assertEqual(summary["exit_boot_services_attempts"], 1)
            self.assertEqual(summary["memory_map_bytes"], OVMF_MEASURED_DESCRIPTOR_COUNT * 48)
            self.assertTrue(summary["boot_completed"])
            self.assertFalse(summary["experimental_page_tables"])
            self.assertFalse(summary["own_page_tables_active"])
            self.assertFalse(summary["triple_fault"])
            self.assertEqual(summary["cr3_pml4_phys"], 0)
            self.assertFalse(summary["wx_enforced"])
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
                self.assertIn("retfq", proc.stdout)
                self.assertNotIn("cr3", proc.stdout)
                self.assertIn("rdtsc", proc.stdout)
                self.assertIn("ud2", proc.stdout)

    def test_cli_experimental_page_tables_report_the_fault(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        example_ks = repo_root / "examples" / "uefi_boot" / "boot.ks"
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cli_main(
                    [
                        "uefi-boot",
                        str(example_ks),
                        "-o",
                        str(Path(tmp) / "BOOTX64.EFI"),
                        "--experimental-page-tables",
                        "--verify-emulate",
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary["experimental_page_tables"])
            self.assertTrue(summary["triple_fault"])
            self.assertFalse(summary["boot_completed"])
            self.assertFalse(summary["own_page_tables_active"])
            self.assertFalse(summary["wx_enforced"])


if __name__ == "__main__":
    unittest.main()
