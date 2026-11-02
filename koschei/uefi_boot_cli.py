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
    UefiBootError,
    build_esp_tree_v1,
    build_fat16_esp_image_v1,
    build_uefi_pe32plus_v1,
    expected_serial_v1,
    simulate_uefi_x86_64_serial_v1,
)


def add_uefi_boot_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "uefi-boot",
        help="Build a bare-metal x86-64 UEFI image (BOOTX64.EFI): COM1 output, ExitBootServices, own GDT/IDT and a COM1 shell",
        description=(
            "Compile a checked, sealed Koschei program into a freestanding x86-64 "
            "UEFI application (BOOTX64.EFI). It prints the program's output on the "
            "16550 UART COM1 (0x3F8) and UEFI ConOut, reads the memory map and "
            "exits the boot services (retrying once with a fresh map key), loads "
            "its own GDT (reloading CS) and 32-gate IDT, masks the 8259 PICs, "
            "programs the 8254 PIT and serves an interactive COM1 shell. Paging "
            "stays the firmware's identity mapping; --experimental-page-tables "
            "adds an unfinished page-table switch that faults on real hardware."
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
        help="Optional output path for a bootable 4 MiB FAT16 ESP disk image (.img), boots under OVMF",
    )
    parser.add_argument(
        "--emit-asm",
        help="Optional output path for a byte-exact listing of the image's .text and .rdata (.s)",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Omit the [KOSCHEI-UEFI-V1] attestation header/footer lines on COM1",
    )
    parser.add_argument(
        "--no-exit-boot-services",
        action="store_true",
        help="Leave the boot services to the firmware: skip GetMemoryMap, ExitBootServices, GDT/IDT, PIC/PIT and the shell",
    )
    parser.add_argument(
        "--no-serial-rx",
        action="store_true",
        help="Halt after the boot report instead of serving the COM1 (0x3F8) shell",
    )
    parser.add_argument(
        "--rx-input",
        default="",
        help="Optional shell line (STATUS, MEM, MIR, EPOCH, TRAP, HALT) to inject into COM1 RX during --verify-emulate",
    )
    parser.add_argument(
        "--halt-mode",
        choices=("return", "halt"),
        default="return",
        help="With --no-exit-boot-services only: 'return' EFI_SUCCESS or 'halt' (cli; hlt); after ExitBootServices the image always halts",
    )
    parser.add_argument(
        "--experimental-page-tables",
        action="store_true",
        help=(
            "EXPERIMENTAL, faults on real hardware: add the Titan page allocator and a "
            "page-table switch (mov cr3) that maps only the two link-address image pages"
        ),
    )
    parser.add_argument(
        "--verify-emulate",
        action="store_true",
        help="Run the built-in x86-64 emulator and require the exact COM1 bytes the image must print",
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
        # The shell needs ExitBootServices; without it there is none to disable.
        enable_rx = exit_bs and not args.no_serial_rx

        artifact = build_uefi_pe32plus_v1(
            mir,
            include_banner=not args.no_banner,
            halt_mode=args.halt_mode,
            exit_boot_services=exit_bs,
            enable_serial_rx=enable_rx,
            experimental_page_tables=args.experimental_page_tables,
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
            expected_serial = expected_serial_v1(
                artifact,
                emulation,
                command=args.rx_input if enable_rx else "",
            )
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
                "code_segment_selector": (
                    emulation.code_segment_selector if emulation else None
                ),
                "exit_boot_services_attempts": (
                    emulation.exit_boot_services_attempts if emulation else None
                ),
                "memory_map_bytes": emulation.memory_map_bytes if emulation else None,
                "experimental_page_tables": artifact.experimental_page_tables,
                "own_page_tables_active": (
                    bool(emulation.cr3_pml4_phys) and not emulation.triple_fault
                    if emulation
                    else None
                ),
                "triple_fault": emulation.triple_fault if emulation else None,
                # "ok" means the image printed exactly what it must; this says
                # whether the emulated boot also got through.
                "boot_completed": (
                    not emulation.triple_fault and not emulation.failure_status
                    if emulation
                    else None
                ),
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
                f"KOSCHEI UEFI BOOT V5: BUILT (target=x86_64-uefi, "
                f"efi={out_path}, sha256={artifact.efi_sha256[:16]}..., "
                f"exit_boot_services={exit_bs}, gdt_idt={exit_bs}, shell={enable_rx}, "
                f"experimental_page_tables={args.experimental_page_tables}, "
                f"emulated={emulation is not None})"
            )
            if emulation is not None:
                print("--- EMULATED COM1 (0x3F8) SERIAL OUTPUT ---")
                print(emulation.serial_text.replace("\r\n", "\n"), end="")
        return 0
    except UefiBootError as error:
        print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1
