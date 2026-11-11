"""CLI subcommand for building Koschei x86-64 UEFI bare-metal boot artifacts (v5)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import cli as _cli
from .mir import require_mir
from .modules import check_graph
from .uefi_boot_v1 import (
    KERNEL_V3_BANNER,
    KERNEL_V4_BANNER,
    KERNEL_V5_BANNER,
    POST_EBS_BANNER,
    SHELL_EPOCH_REPLY,
    SHELL_HALT_REPLY,
    SHELL_MEM_REPLY,
    SHELL_STATUS_REPLY,
    UART_RX_PREFIX,
    UefiBootError,
    build_esp_tree_v1,
    build_fat16_esp_image_v1,
    build_uefi_pe32plus_v1,
    simulate_uefi_x86_64_serial_v1,
)


def add_uefi_boot_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "uefi-boot",
        help="Build a bare-metal x86-64 UEFI (BOOTX64.EFI) kernel with GDT/IDT, Titan PMM, W^X CR3, PIC/PIT/TSC & Shell",
        description=(
            "Compile a checked, sealed Koschei program into a freestanding x86-64 "
            "UEFI kernel (BOOTX64.EFI) with 16550 UART COM1 (0x3F8) TX/RX, "
            "BootServices->GetMemoryMap, BootServices->ExitBootServices, "
            "64-bit GDT (lgdt), 32-gate IDT (lidt), Titan Page Frame Allocator, "
            "4-level W^X Page Tables (mov cr3, rax), 8259 PIC remap/mask, "
            "8254 PIT 1000Hz timer, TSC monotonic clock, and interactive COM1 shell."
        ),
    )
    parser.add_argument("source", help="Koschei source file or project directory")
    parser.add_argument(
        "-o",
        "--output",
        default="BOOTX64.EFI",
        help="Output path for the PE32+ UEFI binary (default: BOOTX64.EFI)",
    )
    parser.add_argument(
        "--esp-dir",
        help="Optional directory to populate with EFI/BOOT/BOOTX64.EFI and startup.nsh",
    )
    parser.add_argument(
        "--esp-image",
        help="Optional output path for a bootable 4 MiB FAT16 ESP disk image (.img)",
    )
    parser.add_argument(
        "--emit-asm",
        help="Optional output path for the freestanding x86-64 Intel-syntax assembly (.s)",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Omit the [KOSCHEI-UEFI-V1] attestation header/footer lines on COM1",
    )
    parser.add_argument(
        "--no-exit-boot-services",
        action="store_true",
        help="Skip GetMemoryMap, ExitBootServices, GDT/IDT, Titan PMM, W^X CR3, and PIC/PIT/TSC",
    )
    parser.add_argument(
        "--no-serial-rx",
        action="store_true",
        help="Disable post-ExitBootServices COM1 (0x3F8) RX line polling and shell",
    )
    parser.add_argument(
        "--rx-input",
        default="",
        help="Optional ASCII command (STATUS, MEM, MIR, EPOCH, HALT) to inject into COM1 RX during --verify-emulate",
    )
    parser.add_argument(
        "--halt-mode",
        choices=("return", "halt"),
        default="return",
        help="Termination mode after serial flush: 'return' EFI_SUCCESS or 'halt' (cli; hlt)",
    )
    parser.add_argument(
        "--verify-emulate",
        action="store_true",
        help="Run the built-in x86-64 PE32+ hardware-port, GDT/IDT, Titan PMM, W^X CR3 & PIC/PIT/TSC emulator",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable build and verification summary JSON",
    )


def command_uefi_boot(args: argparse.Namespace) -> int:
    try:
        graph = _cli.open_graph(args.source)
        check_graph(graph)
        mir = require_mir(graph)
        exit_bs = not args.no_exit_boot_services
        enable_rx = not args.no_serial_rx

        artifact = build_uefi_pe32plus_v1(
            mir,
            include_banner=not args.no_banner,
            halt_mode=args.halt_mode,
            exit_boot_services=exit_bs,
            enable_serial_rx=enable_rx,
        )
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(artifact.efi_bytes)

        esp_efi_path = None
        if args.esp_dir:
            esp_efi_path = str(build_esp_tree_v1(artifact, Path(args.esp_dir)))

        esp_img_path = None
        if args.esp_image:
            img_target = Path(args.esp_image)
            img_target.parent.mkdir(parents=True, exist_ok=True)
            img_bytes = build_fat16_esp_image_v1(artifact)
            img_target.write_bytes(img_bytes)
            esp_img_path = str(img_target)

        asm_path = None
        if args.emit_asm:
            asm_target = Path(args.emit_asm)
            asm_target.parent.mkdir(parents=True, exist_ok=True)
            asm_target.write_text(artifact.assembly_source, encoding="utf-8")
            asm_path = str(asm_target)

        emulation = None
        if args.verify_emulate:
            rx_bytes = (
                (args.rx_input + "\n").encode("utf-8") if args.rx_input else b""
            )
            emulation = simulate_uefi_x86_64_serial_v1(
                artifact.efi_bytes,
                rx_input=rx_bytes,
            )
            expected_serial = artifact.serial_payload
            if exit_bs:
                expected_serial += (
                    POST_EBS_BANNER
                    + KERNEL_V3_BANNER
                    + KERNEL_V4_BANNER
                    + KERNEL_V5_BANNER
                )
            if enable_rx and args.rx_input:
                cmd_raw = args.rx_input.encode("utf-8")[:48]
                expected_serial += UART_RX_PREFIX + cmd_raw + b"\r\n"
                if cmd_raw.startswith(b"STAT"):
                    expected_serial += SHELL_STATUS_REPLY
                elif cmd_raw == b"MEM":
                    expected_serial += SHELL_MEM_REPLY
                elif cmd_raw == b"MIR":
                    expected_serial += (
                        f"[KOSCHEI-SHELL] sealed_mir_sha256={artifact.mir_fingerprint}\r\n".encode(
                            "utf-8"
                        )
                    )
                elif cmd_raw.startswith(b"EPOC"):
                    expected_serial += SHELL_EPOCH_REPLY
                elif cmd_raw.startswith(b"HALT"):
                    expected_serial += SHELL_HALT_REPLY
            if emulation.serial_bytes != expected_serial:
                raise UefiBootError(
                    "KS4013",
                    "emulated COM1 serial stream diverged from expected bare-metal payload",
                )

        if args.json:
            payload = {
                "ok": True,
                "target": "x86_64-unknown-uefi",
                "subsystem": 10,
                "serial_port": "COM1 (0x3F8, 115200 8N1, TX+RX+Shell)",
                "mir_fingerprint": artifact.mir_fingerprint,
                "efi_path": str(out_path),
                "efi_sha256": artifact.efi_sha256,
                "efi_size_bytes": len(artifact.efi_bytes),
                "serial_payload_bytes": len(artifact.serial_payload),
                "exit_boot_services_enabled": exit_bs,
                "serial_rx_enabled": enable_rx,
                "esp_efi_path": esp_efi_path,
                "esp_image_path": esp_img_path,
                "assembly_path": asm_path,
                "verified_emulation": bool(emulation is not None),
                "memory_map_acquired": (
                    emulation.memory_map_acquired if emulation else None
                ),
                "exit_boot_services_called": (
                    emulation.exit_boot_services_called if emulation else None
                ),
                "boot_services_tombstoned": (
                    emulation.boot_services_tombstoned if emulation else None
                ),
                "gdt_loaded": emulation.gdt_loaded if emulation else None,
                "idt_loaded": emulation.idt_loaded if emulation else None,
                "idt_gate_count": emulation.idt_gate_count if emulation else None,
                "titan_total_usable_pages": (
                    emulation.titan_total_usable_pages if emulation else None
                ),
                "titan_allocated_page_phys": (
                    emulation.titan_allocated_page_phys if emulation else None
                ),
                "titan_remaining_pages": (
                    emulation.titan_remaining_pages if emulation else None
                ),
                "cr3_pml4_phys": emulation.cr3_pml4_phys if emulation else None,
                "wx_enforced": emulation.wx_enforced if emulation else None,
                "pic_remapped_and_masked": (
                    emulation.pic_remapped_and_masked if emulation else None
                ),
                "pit_divisor": emulation.pit_divisor if emulation else None,
                "active_epoch": emulation.active_epoch if emulation else None,
                "emulated_instructions": (
                    emulation.instructions_executed if emulation else None
                ),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"KOSCHEI UEFI BOOT V5: PASS (target=x86_64-uefi, "
                f"efi={out_path}, sha256={artifact.efi_sha256[:16]}..., "
                f"gdt_idt={exit_bs}, wx_cr3={exit_bs}, pic_pit_tsc={exit_bs}, shell={enable_rx})"
            )
            if emulation is not None:
                print("--- EMULATED COM1 (0x3F8) SERIAL OUTPUT ---")
                print(emulation.serial_text.replace("\r\n", "\n"), end="")
        return 0
    except UefiBootError as error:
        print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1
