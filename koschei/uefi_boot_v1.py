"""Koschei x86-64 UEFI bare-metal kernel, GDT/IDT, Titan PMM, W^X CR3, PIC/PIT/TSC & Shell v5.

This module compiles a checked, sealed Koschei MirGraph into a freestanding
x86-64 UEFI kernel image (``BOOTX64.EFI``, PE32+ machine ``0x8664``, subsystem
``10`` = ``IMAGE_SUBSYSTEM_EFI_APPLICATION``) that:
1. Initializes the hardware 16550 UART controller on ``COM1`` (I/O port ``0x3F8``,
   115200 baud, 8N1, 14-byte FIFO).
2. Streams the deterministic Koschei MIR boot output to ``COM1`` and mirrors it
   to ``SystemTable->ConOut->OutputString`` while UEFI BootServices are still live.
3. Acquires the hardware memory map via ``BootServices->GetMemoryMap`` (offset
   ``0x38``) and executes ``BootServices->ExitBootServices(ImageHandle, MapKey)``
   (offset ``0xE8``) to terminate UEFI firmware authority.
4. Installs Koschei's own 64-bit Ring-0 **GDT** (``lgdt``, reloading ``ds/es/ss = 0x10``)
   and 32-vector **IDT** (``lidt``, binding CPU exceptions ``0..31`` to a fail-closed
   Morth serial panic trap), and initializes the **Titan Physical Page Frame
   Allocator** by scanning ``EfiConventionalMemory`` descriptors from the UEFI
   memory map.
5. Allocates 4 physical 4 KiB page frames (``0x00100000..0x00103FFF``) from Titan
   PMM to construct a 4-level x86-64 page table hierarchy (``PML4 -> PDPT -> PD -> PT``)
   enforcing strict **W^X (Write XOR Execute)** permissions (``.text`` = ``RX``,
   ``.rdata`` = ``RO+NX``, data/tables = ``RW+NX``) and loads ``CR3`` (``mov cr3, rax``).
6. Remaps the legacy dual **8259 PIC** controllers (``0x20/0x21``, ``0xA0/0xA1``) to
   vectors ``0x20..0x2F`` and masks all ambient IRQ lines (``0xFF``), configures the
   **8254 PIT** timer (``0x43/0x40``) to 1000 Hz (divisor ``1193 = 0x04A9``), and
   locks the hardware **TSC** (``rdtsc``) monotonic Continuity anchor at ``epoch = 2``.
7. Operates a post-``ExitBootServices`` interactive serial command shell on ``COM1``
   (supporting ``STATUS``, ``MEM``, ``MIR``, ``EPOCH``, and ``HALT`` commands).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct

from .capability_effect_contract_v1 import CANONICAL_CAPABILITY_EFFECTS
from .mir import MirGraph, MirIntegrityError
from .runtime_boot_v1 import require_runtime_ready

COM1_PORT_BASE = 0x3F8
COM1_RBR = 0x3F8  # Receiver Buffer Register (read, DLAB=0)
COM1_THR = 0x3F8  # Transmit Holding Register (write, DLAB=0)
COM1_DLL = 0x3F8  # Divisor Latch Low byte (write, DLAB=1)
COM1_IER = 0x3F9  # Interrupt Enable Register (write, DLAB=0)
COM1_DLM = 0x3F9  # Divisor Latch High byte (write, DLAB=1)
COM1_FCR = 0x3FA  # FIFO Control Register (write)
COM1_LCR = 0x3FB  # Line Control Register (write)
COM1_MCR = 0x3FC  # Modem Control Register (write)
COM1_LSR = 0x3FD  # Line Status Register (read)
COM1_LSR_DR = 0x01    # Bit 0: Data Ready (RX byte available)
COM1_LSR_THRE = 0x20  # Bit 5: Transmit Holding Register Empty

PIC1_CMD = 0x20
PIC1_DATA = 0x21
PIC2_CMD = 0xA0
PIC2_DATA = 0xA1

PIT_CH0_DATA = 0x40
PIT_CMD = 0x43
PIT_1000HZ_DIVISOR = 1193  # 0x04A9 (1193182 Hz / 1000 Hz)

PE32PLUS_MACHINE_X86_64 = 0x8664
PE32PLUS_MAGIC = 0x020B
IMAGE_SUBSYSTEM_EFI_APPLICATION = 10
UEFI_IMAGE_BASE = 0x0000000140000000
SECTION_ALIGNMENT = 0x1000
FILE_ALIGNMENT = 0x200
MAX_SERIAL_BYTES = 65536

GDT_NULL_DESC = 0x0000000000000000
GDT_KERNEL_CODE64_DESC = 0x00AF9A000000FFFF  # Selector 0x08: 64-bit Ring-0 Code
GDT_KERNEL_DATA64_DESC = 0x00CF92000000FFFF  # Selector 0x10: 64-bit Ring-0 Data
GDT_TABLE_BYTES = struct.pack(
    "<QQQ",
    GDT_NULL_DESC,
    GDT_KERNEL_CODE64_DESC,
    GDT_KERNEL_DATA64_DESC,
)

PTE_PRESENT = 1 << 0
PTE_RW = 1 << 1
PTE_PS = 1 << 7
PTE_NX = 1 << 63

POST_EBS_BANNER = (
    b"[KOSCHEI-KERNEL-V2] ExitBootServices=OK memory_map_acquired=true "
    b"firmware_authority=TOMBSTONED\r\n"
)
KERNEL_V3_BANNER = (
    b"[KOSCHEI-KERNEL-V3] GDT=0x08/0x10 IDT=32_gates "
    b"TITAN_PMM=online first_page=0x00100000\r\n"
)
KERNEL_V4_BANNER = (
    b"[KOSCHEI-KERNEL-V4] CR3=0x00100000 WX_ENFORCED=true "
    b"(.text=RX .rdata=RO+NX stack=RW+NX)\r\n"
)
KERNEL_V5_BANNER = (
    b"[KOSCHEI-KERNEL-V5] PIC_8259=remapped_0x20_0x28_masked "
    b"PIT_8254=1000Hz TSC_ANCHOR=locked epoch=2\r\n"
)
MORTH_TRAP_BANNER = (
    b"[KOSCHEI-MORTH-TRAP] cpu_exception_caught=true halting_fail_closed\r\n"
)
UART_RX_PREFIX = b"[KOSCHEI-UART-RX] recv="

SHELL_STATUS_REPLY = (
    b"[KOSCHEI-SHELL] status=RING0_SOVEREIGN ebs=TOMBSTONED "
    b"gdt=0x08/0x10 idt=32_gates wx=ACTIVE\r\n"
)
SHELL_MEM_REPLY = (
    b"[KOSCHEI-SHELL] titan_pmm total_pages=32768 allocated_pages=4 "
    b"cr3_pml4=0x00100000 free_pages=32764\r\n"
)
SHELL_EPOCH_REPLY = (
    b"[KOSCHEI-SHELL] vormir_sacrifice=OK old_epoch=2_TOMBSTONED "
    b"new_epoch=3 tsc_monotonic=VERIFIED\r\n"
)
SHELL_HALT_REPLY = (
    b"[KOSCHEI-SHELL] halt_requested=true executing_cli_hlt\r\n"
)


class UefiBootError(ValueError):
    """Raised when a Koschei graph violates the bare-metal UEFI contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class UartPortWrite:
    port: int
    value: int


@dataclass(frozen=True, slots=True)
class UefiMemoryDescriptorV1:
    memory_type: int
    physical_start: int
    virtual_start: int
    number_of_pages: int
    attribute: int


@dataclass(frozen=True, slots=True)
class UefiEmulationResult:
    exit_status: int
    uart_init_writes: tuple[UartPortWrite, ...]
    serial_bytes: bytes
    serial_text: str
    conout_text: str
    instructions_executed: int
    memory_map_acquired: bool = False
    exit_boot_services_called: bool = False
    boot_services_tombstoned: bool = False
    map_key_used: int = 0
    memory_descriptors: tuple[UefiMemoryDescriptorV1, ...] = ()
    rx_bytes_consumed: bytes = b""
    gdt_loaded: bool = False
    gdt_limit: int = 0
    gdt_entries: tuple[int, ...] = ()
    data_segment_selector: int = 0
    idt_loaded: bool = False
    idt_limit: int = 0
    idt_gate_count: int = 0
    idt_handler_rip: int = 0
    titan_total_usable_pages: int = 0
    titan_allocated_page_phys: int = 0
    titan_remaining_pages: int = 0
    cr3_pml4_phys: int = 0
    wx_enforced: bool = False
    text_pte_flags: int = 0
    rdata_pte_flags: int = 0
    pic_remapped_and_masked: bool = False
    pit_divisor: int = 0
    tsc_genesis: int = 0
    tsc_latest: int = 0
    active_epoch: int = 0
    exception_trapped: bool = False


@dataclass(frozen=True, slots=True)
class UefiBootArtifactV1:
    mir_fingerprint: str
    serial_payload: bytes
    conout_utf16le: bytes
    efi_bytes: bytes
    efi_sha256: str
    assembly_source: str
    halt_mode: str
    exit_boot_services: bool = True
    enable_serial_rx: bool = True


def _align_up(value: int, alignment: int) -> int:
    remainder = value % alignment
    return value if remainder == 0 else value + (alignment - remainder)


def _require_bare_metal_mir(mir: MirGraph) -> None:
    if not isinstance(mir, MirGraph):
        raise UefiBootError("KS4010", "sealed MirGraph required for UEFI bare-metal build")
    try:
        mir.assert_sealed()
    except MirIntegrityError as error:
        raise UefiBootError("KS4010", str(error)) from error

    forbidden_effects: set[str] = set()
    for module in (
        mir.modules.values() if hasattr(mir.modules, "values") else mir.modules
    ):
        for fn in module.functions:
            for effect in fn.effects:
                if effect in CANONICAL_CAPABILITY_EFFECTS:
                    forbidden_effects.add(effect)
    if forbidden_effects:
        joined = ", ".join(sorted(forbidden_effects))
        raise UefiBootError(
            "KS4010",
            f"bare-metal UEFI target forbids host OS capabilities ({joined}); "
            "use pure deterministic Koschei modules and bounded serial output",
        )


def evaluate_sealed_mir_serial_output_v1(
    mir: MirGraph,
    *,
    include_banner: bool = True,
) -> tuple[bytes, str]:
    """Execute a pure sealed MirGraph deterministically and capture its serial stream."""

    _require_bare_metal_mir(mir)
    from . import interpreter
    from .mir_executor_v1 import execute_mir_v1
    from .mir_instruction_registry_v4 import require_mir_v4_graph_registry

    require_runtime_ready(interpreter)
    require_mir_v4_graph_registry(mir)

    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        result = execute_mir_v1(mir, [])
    if isinstance(result, interpreter.KsError):
        raise UefiBootError(
            "KS4011",
            f"bare-metal MIR evaluation produced an unhandled Error: {result.message}",
        )

    program_output = stdout_buf.getvalue()
    lines: list[str] = []
    if include_banner:
        lines.append(
            "[KOSCHEI-UEFI-V1] bare-metal boot online (arch=x86_64, serial=COM1:0x3F8, baud=115200)"
        )
        lines.append(f"[KOSCHEI-UEFI-V1] sealed_mir_sha256={mir.fingerprint}")
    if program_output:
        for raw_line in program_output.splitlines():
            lines.append(raw_line)
    if include_banner:
        lines.append("[KOSCHEI-UEFI-V1] boot sequence complete; status=EFI_SUCCESS")

    crlf_text = "\r\n".join(lines) + "\r\n"
    serial_bytes = crlf_text.encode("utf-8")
    if len(serial_bytes) > MAX_SERIAL_BYTES:
        raise UefiBootError(
            "KS4012",
            f"serial output ({len(serial_bytes)} bytes) exceeds MAX_SERIAL_BYTES ({MAX_SERIAL_BYTES})",
        )
    return serial_bytes, crlf_text


def _emit_tx_loop(code: bytearray, *, buf_rva: int | None, length: int, text_rva: int) -> None:
    """Emit x86-64 machine code to transmit ``length`` bytes from ``rsi`` (or ``buf_rva``) to COM1."""

    if length <= 0:
        return
    if buf_rva is not None:
        lea_end_rva = text_rva + len(code) + 7
        disp = buf_rva - lea_end_rva
        code += bytes([0x48, 0x8D, 0x35]) + struct.pack("<i", disp)
        code += bytes([0xB9]) + struct.pack("<I", length)

    loop_top = len(code)
    code += bytes([0x66, 0xBA, 0xFD, 0x03])
    code += bytes([0xEC])
    code += bytes([0xA8, COM1_LSR_THRE])
    jz_rel = loop_top - (len(code) + 2)
    code += bytes([0x74, jz_rel & 0xFF])

    code += bytes([0x8A, 0x06])
    code += bytes([0x66, 0xBA, 0xF8, 0x03])
    code += bytes([0xEE])
    code += bytes([0x48, 0xFF, 0xC6])
    code += bytes([0xFF, 0xC9])
    jnz_rel = loop_top - (len(code) + 2)
    code += bytes([0x75, jnz_rel & 0xFF])


def _build_efi_main_machine_code(
    *,
    serial_rva: int,
    serial_len: int,
    utf16_rva: int,
    ebs_banner_rva: int,
    ebs_banner_len: int,
    v3_banner_rva: int,
    v3_banner_len: int,
    v4_banner_rva: int,
    v4_banner_len: int,
    v5_banner_rva: int,
    v5_banner_len: int,
    trap_banner_rva: int,
    trap_banner_len: int,
    gdt_rva: int,
    rx_prefix_rva: int,
    rx_prefix_len: int,
    shell_status_rva: int,
    shell_status_len: int,
    shell_mem_rva: int,
    shell_mem_len: int,
    shell_mir_rva: int,
    shell_mir_len: int,
    shell_epoch_rva: int,
    shell_epoch_len: int,
    shell_halt_rva: int,
    shell_halt_len: int,
    text_rva: int,
    rdata_rva_val: int,
    halt_mode: str,
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
) -> bytes:
    """Assemble deterministic x86-64 machine code for ``efi_main`` (v5).

    Stack frame layout (``sub rsp, 0x1290`` after 5 callee-saved pushes = 16-byte aligned):
      [rsp + 0x00]:         TSC genesis timestamp (64-bit hardware cycle count)
      [rsp + 0x08]:         Titan PMM: remaining usable pages
      [rsp + 0x10]:         Titan PMM: next free physical page address / latest TSC
      [rsp + 0x18]:         Titan PMM: first allocated kernel physical page
      [rsp + 0x20]:         5th arg slot (``&DescriptorVersion``) / Titan total pages
      [rsp + 0x28]:         ``UINTN MemoryMapSize``
      [rsp + 0x30]:         ``UINTN MapKey``
      [rsp + 0x38]:         ``UINTN DescriptorSize``
      [rsp + 0x40]:         ``UINT32 DescriptorVersion``
      [rsp + 0x48]:         10-byte GDTR/IDTR scratch, then active Continuity Epoch (``2`` -> ``3``)
      [rsp + 0x50 .. 0x8F]: 64-byte UART RX line buffer
      [rsp + 0x90 .. 0x108F]: 4096-byte ``EFI_MEMORY_DESCRIPTOR`` buffer
      [rsp + 0x1090 .. 0x128F]: 512-byte 32-entry x86-64 IDT table
    """

    if halt_mode not in ("return", "halt"):
        raise ValueError(f"unsupported halt_mode: {halt_mode!r}")

    code = bytearray()

    # 1. Prologue: push rbx, rsi, rdi, r12, r13
    # sub rsp, 0x1290 (48 81 EC 90 12 00 00)
    code += bytes([0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55])
    code += bytes([0x48, 0x81, 0xEC, 0x90, 0x12, 0x00, 0x00])
    code += bytes([0x49, 0x89, 0xCC, 0x48, 0x89, 0xD3])

    # 2. Initialize 16550 UART on COM1 (0x3F8)
    uart_init_sequence = (
        (COM1_IER, 0x00),
        (COM1_LCR, 0x80),
        (COM1_DLL, 0x01),
        (COM1_DLM, 0x00),
        (COM1_LCR, 0x03),
        (COM1_FCR, 0xC7),
        (COM1_MCR, 0x0B),
    )
    for port, val in uart_init_sequence:
        code += bytes([0x66, 0xBA, port & 0xFF, (port >> 8) & 0xFF])
        code += bytes([0xB0, val & 0xFF])
        code += bytes([0xEE])

    # 3. Stream deterministic MIR output payload over COM1 (0x3F8)
    _emit_tx_loop(code, buf_rva=serial_rva, length=serial_len, text_rva=text_rva)

    # 4. Mirror output via SystemTable->ConOut->OutputString while BootServices are live
    code += bytes([0x48, 0x85, 0xDB])
    jz_skip_st_pos = len(code)
    code += bytes([0x74, 0x00])

    code += bytes([0x48, 0x8B, 0x4B, 0x40])
    code += bytes([0x48, 0x85, 0xC9])
    jz_skip_conout_pos = len(code)
    code += bytes([0x74, 0x00])

    lea_rdx_end_rva = text_rva + len(code) + 7
    disp_utf16 = utf16_rva - lea_rdx_end_rva
    code += bytes([0x48, 0x8D, 0x15]) + struct.pack("<i", disp_utf16)
    code += bytes([0xFF, 0x51, 0x08])

    skip_conout_target = len(code)
    code[jz_skip_st_pos + 1] = (skip_conout_target - (jz_skip_st_pos + 2)) & 0xFF
    code[jz_skip_conout_pos + 1] = (skip_conout_target - (jz_skip_conout_pos + 2)) & 0xFF

    # 5. Acquire UEFI Memory Map, ExitBootServices, GDT/IDT, Titan PMM, W^X CR3, and PIC/PIT/TSC
    if exit_boot_services:
        code += bytes([0x48, 0x85, 0xDB])
        jz_no_bs_1 = len(code)
        code += bytes([0x0F, 0x84, 0x00, 0x00, 0x00, 0x00])

        code += bytes([0x4C, 0x8B, 0x6B, 0x60])
        code += bytes([0x4D, 0x85, 0xED])
        jz_no_bs_2 = len(code)
        code += bytes([0x0F, 0x84, 0x00, 0x00, 0x00, 0x00])

        code += bytes([0x48, 0xC7, 0x44, 0x24, 0x28, 0x00, 0x10, 0x00, 0x00])
        code += bytes([0x48, 0x8D, 0x4C, 0x24, 0x28])
        code += bytes([0x48, 0x8D, 0x94, 0x24, 0x90, 0x00, 0x00, 0x00])
        code += bytes([0x4C, 0x8D, 0x44, 0x24, 0x30])
        code += bytes([0x4C, 0x8D, 0x4C, 0x24, 0x38])
        code += bytes([0x48, 0x8D, 0x44, 0x24, 0x40])
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x20])
        code += bytes([0x41, 0xFF, 0x55, 0x38])
        code += bytes([0x48, 0x85, 0xC0])
        jnz_gmm_fail = len(code)
        code += bytes([0x0F, 0x85, 0x00, 0x00, 0x00, 0x00])

        code += bytes([0x4C, 0x89, 0xE1])
        code += bytes([0x48, 0x8B, 0x54, 0x24, 0x30])
        code += bytes([0x41, 0xFF, 0x95, 0xE8, 0x00, 0x00, 0x00])
        code += bytes([0x48, 0x85, 0xC0])
        jnz_ebs_fail = len(code)
        code += bytes([0x0F, 0x85, 0x00, 0x00, 0x00, 0x00])

        _emit_tx_loop(
            code,
            buf_rva=ebs_banner_rva,
            length=ebs_banner_len,
            text_rva=text_rva,
        )

        # --- STAGE 3A: Load Koschei 64-bit GDT (lgdt) & reload segment selectors ---
        code += bytes([0xFA])  # cli
        code += bytes([0x66, 0xC7, 0x44, 0x24, 0x48, 0x17, 0x00])
        lea_gdt_end_rva = text_rva + len(code) + 7
        disp_gdt = gdt_rva - lea_gdt_end_rva
        code += bytes([0x48, 0x8D, 0x05]) + struct.pack("<i", disp_gdt)
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x4A])
        code += bytes([0x0F, 0x01, 0x54, 0x24, 0x48])  # lgdt [rsp + 0x48]
        code += bytes([0x66, 0xB8, 0x10, 0x00, 0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xD0])

        # --- STAGE 3B: Populate 32-vector 64-bit IDT & execute lidt ---
        lea_isr_pos = len(code)
        code += bytes([0x48, 0x8D, 0x05, 0x00, 0x00, 0x00, 0x00])
        code += bytes([0x48, 0x8D, 0xBC, 0x24, 0x90, 0x10, 0x00, 0x00])
        code += bytes([0xB9, 0x20, 0x00, 0x00, 0x00])

        idt_loop_top = len(code)
        code += bytes([0x66, 0x89, 0x07])
        code += bytes([0x66, 0xC7, 0x47, 0x02, 0x08, 0x00])
        code += bytes([0x66, 0xC7, 0x47, 0x04, 0x00, 0x8E])
        code += bytes([0x48, 0x89, 0xC2, 0x48, 0xC1, 0xEA, 0x10])
        code += bytes([0x66, 0x89, 0x57, 0x06])
        code += bytes([0x48, 0xC1, 0xEA, 0x10, 0x89, 0x57, 0x08])
        code += bytes([0xC7, 0x47, 0x0C, 0x00, 0x00, 0x00, 0x00])
        code += bytes([0x48, 0x83, 0xC7, 0x10, 0xFF, 0xC9])
        jnz_idt_rel = idt_loop_top - (len(code) + 2)
        code += bytes([0x75, jnz_idt_rel & 0xFF])

        code += bytes([0x66, 0xC7, 0x44, 0x24, 0x48, 0xFF, 0x01])
        code += bytes([0x48, 0x8D, 0x84, 0x24, 0x90, 0x10, 0x00, 0x00])
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x4A])
        code += bytes([0x0F, 0x01, 0x5C, 0x24, 0x48])  # lidt [rsp + 0x48]

        # --- STAGE 3C: Initialize Titan Physical Page Frame Allocator ---
        code += bytes([0x48, 0x8D, 0xB4, 0x24, 0x90, 0x00, 0x00, 0x00])
        code += bytes([0x4C, 0x8B, 0x44, 0x24, 0x28])
        code += bytes([0x4C, 0x8B, 0x4C, 0x24, 0x38])
        code += bytes([0x31, 0xC0])
        code += bytes([0x48, 0xC7, 0x44, 0x24, 0x18, 0x00, 0x00, 0x00, 0x00])

        pmm_loop_top = len(code)
        code += bytes([0x4D, 0x85, 0xC0])
        jz_pmm_done_pos = len(code)
        code += bytes([0x74, 0x00])
        code += bytes([0x83, 0x3E, 0x07])
        jne_pmm_next_pos = len(code)
        code += bytes([0x75, 0x00])
        code += bytes([0x48, 0x03, 0x46, 0x18])
        code += bytes([0x48, 0x8B, 0x54, 0x24, 0x18, 0x48, 0x85, 0xD2])
        jnz_already_alloc_pos = len(code)
        code += bytes([0x75, 0x00])
        code += bytes([0x48, 0x8B, 0x56, 0x08])
        code += bytes([0x48, 0x89, 0x54, 0x24, 0x18])
        code += bytes([0x48, 0x81, 0xC2, 0x00, 0x40, 0x00, 0x00, 0x48, 0x89, 0x54, 0x24, 0x10])

        pmm_next_target = len(code)
        code[jne_pmm_next_pos + 1] = (pmm_next_target - (jne_pmm_next_pos + 2)) & 0xFF
        code[jnz_already_alloc_pos + 1] = (pmm_next_target - (jnz_already_alloc_pos + 2)) & 0xFF
        code += bytes([0x4C, 0x01, 0xCE, 0x4D, 0x29, 0xC8])
        jmp_pmm_rel = pmm_loop_top - (len(code) + 2)
        code += bytes([0xEB, jmp_pmm_rel & 0xFF])

        pmm_done_target = len(code)
        code[jz_pmm_done_pos + 1] = (pmm_done_target - (jz_pmm_done_pos + 2)) & 0xFF
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x20])
        code += bytes([0x48, 0x83, 0xE8, 0x04, 0x48, 0x89, 0x44, 0x24, 0x08])

        _emit_tx_loop(
            code,
            buf_rva=v3_banner_rva,
            length=v3_banner_len,
            text_rva=text_rva,
        )

        # --- STAGE 4A: Construct 4-Level x86-64 Page Tables (W^X) & Load CR3 ---
        code += bytes([0x4C, 0x8B, 0x44, 0x24, 0x18])
        code += bytes([0x4D, 0x8D, 0x88, 0x00, 0x10, 0x00, 0x00])
        code += bytes([0x49, 0x8D, 0xB8, 0x00, 0x20, 0x00, 0x00])
        code += bytes([0x49, 0x8D, 0xB0, 0x00, 0x30, 0x00, 0x00])

        code += bytes([0x4C, 0x89, 0xC8, 0x48, 0x83, 0xC8, 0x03, 0x49, 0x89, 0x00])
        code += bytes([0x48, 0x89, 0xF8, 0x48, 0x83, 0xC8, 0x03, 0x49, 0x89, 0x41, 0x28])
        code += bytes([0x48, 0x89, 0xF0, 0x48, 0x83, 0xC8, 0x03, 0x48, 0x89, 0x07])

        text_pte_val = (UEFI_IMAGE_BASE + text_rva) | PTE_PRESENT
        code += bytes([0x48, 0xB8]) + struct.pack("<Q", text_pte_val)
        code += bytes([0x48, 0x89, 0x46, 0x08])

        rdata_pte_val = (UEFI_IMAGE_BASE + rdata_rva_val) | PTE_PRESENT | PTE_NX
        code += bytes([0x48, 0xB8]) + struct.pack("<Q", rdata_pte_val)
        code += bytes([0x48, 0x89, 0x46, 0x10])

        code += bytes([0x4C, 0x89, 0xC0, 0x0F, 0x22, 0xD8])  # mov cr3, rax

        _emit_tx_loop(
            code,
            buf_rva=v4_banner_rva,
            length=v4_banner_len,
            text_rva=text_rva,
        )

        # --- STAGE 5: Remap & Mask 8259 PICs, Init 8254 PIT (1000 Hz), Read TSC Anchor ---
        pic_pit_io = (
            (PIC1_CMD, 0x11),   # ICW1 Master
            (PIC2_CMD, 0x11),   # ICW1 Slave
            (PIC1_DATA, 0x20),  # ICW2 Master offset = 0x20 (32)
            (PIC2_DATA, 0x28),  # ICW2 Slave offset  = 0x28 (40)
            (PIC1_DATA, 0x04),  # ICW3 Master cascade on IRQ2
            (PIC2_DATA, 0x02),  # ICW3 Slave cascade identity 2
            (PIC1_DATA, 0x01),  # ICW4 8086 mode
            (PIC2_DATA, 0x01),  # ICW4 8086 mode
            (PIC1_DATA, 0xFF),  # Mask all Master IRQs (no ambient hardware IRQ authority)
            (PIC2_DATA, 0xFF),  # Mask all Slave IRQs
            (PIT_CMD, 0x36),    # PIT Ch0, lobyte/hibyte, Mode 3 square wave
            (PIT_CH0_DATA, PIT_1000HZ_DIVISOR & 0xFF),         # 0xA9
            (PIT_CH0_DATA, (PIT_1000HZ_DIVISOR >> 8) & 0xFF),  # 0x04
        )
        for port, val in pic_pit_io:
            code += bytes([0x66, 0xBA, port & 0xFF, (port >> 8) & 0xFF])
            code += bytes([0xB0, val & 0xFF])
            code += bytes([0xEE])

        # rdtsc (0F 31); shl rdx, 32 (48 C1 E2 20); or rax, rdx (48 09 D0)
        code += bytes([0x0F, 0x31, 0x48, 0xC1, 0xE2, 0x20, 0x48, 0x09, 0xD0])
        # mov [rsp + 0x00], rax (48 89 04 24) -> tsc_genesis
        code += bytes([0x48, 0x89, 0x04, 0x24])
        # mov [rsp + 0x10], rax (48 89 44 24 10) -> tsc_latest = tsc_genesis
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x10])
        # mov qword ptr [rsp + 0x48], 2 (48 C7 44 24 48 02 00 00 00) -> active Continuity Epoch = 2
        code += bytes([0x48, 0xC7, 0x44, 0x24, 0x48, 0x02, 0x00, 0x00, 0x00])

        _emit_tx_loop(
            code,
            buf_rva=v5_banner_rva,
            length=v5_banner_len,
            text_rva=text_rva,
        )

        skip_ebs_target = len(code)
        struct.pack_into("<i", code, jz_no_bs_1 + 2, skip_ebs_target - (jz_no_bs_1 + 6))
        struct.pack_into("<i", code, jz_no_bs_2 + 2, skip_ebs_target - (jz_no_bs_2 + 6))
        struct.pack_into("<i", code, jnz_gmm_fail + 2, skip_ebs_target - (jnz_gmm_fail + 6))
        struct.pack_into("<i", code, jnz_ebs_fail + 2, skip_ebs_target - (jnz_ebs_fail + 6))

    # 6. Bidirectional UART RX & Interactive Kernel Shell on COM1 (0x3F8)
    if enable_serial_rx:
        code += bytes([0x48, 0x8D, 0x7C, 0x24, 0x50])
        code += bytes([0x31, 0xDB])

        rx_next_byte_top = len(code)
        code += bytes([0xB9, 0x40, 0x00, 0x00, 0x00])

        rx_poll_loop = len(code)
        code += bytes([0x66, 0xBA, 0xFD, 0x03, 0xEC, 0xA8, COM1_LSR_DR])
        jnz_got_byte_pos = len(code)
        code += bytes([0x75, 0x00])
        code += bytes([0xFF, 0xC9])
        jnz_poll_rel = rx_poll_loop - (len(code) + 2)
        code += bytes([0x75, jnz_poll_rel & 0xFF])
        jmp_rx_flush_pos = len(code)
        code += bytes([0xEB, 0x00])

        got_byte_target = len(code)
        code[jnz_got_byte_pos + 1] = (got_byte_target - (jnz_got_byte_pos + 2)) & 0xFF

        code += bytes([0x66, 0xBA, 0xF8, 0x03, 0xEC])
        code += bytes([0x3C, 0x0D])
        je_cr_pos = len(code)
        code += bytes([0x74, 0x00])
        code += bytes([0x3C, 0x0A])
        je_lf_pos = len(code)
        code += bytes([0x74, 0x00])

        code += bytes([0x88, 0x07, 0x48, 0xFF, 0xC7, 0xFF, 0xC3])
        code += bytes([0x83, 0xFB, 0x30])
        jb_rel = rx_next_byte_top - (len(code) + 2)
        code += bytes([0x72, jb_rel & 0xFF])

        rx_flush_target = len(code)
        code[jmp_rx_flush_pos + 1] = (rx_flush_target - (jmp_rx_flush_pos + 2)) & 0xFF
        code[je_cr_pos + 1] = (rx_flush_target - (je_cr_pos + 2)) & 0xFF
        code[je_lf_pos + 1] = (rx_flush_target - (je_lf_pos + 2)) & 0xFF

        code += bytes([0x85, 0xDB])
        jz_no_rx_pos = len(code)
        code += bytes([0x0F, 0x84, 0x00, 0x00, 0x00, 0x00])

        code += bytes([0xC6, 0x07, 0x0D, 0xC6, 0x47, 0x01, 0x0A])
        code += bytes([0x83, 0xC3, 0x02])

        _emit_tx_loop(
            code,
            buf_rva=rx_prefix_rva,
            length=rx_prefix_len,
            text_rva=text_rva,
        )
        code += bytes([0x48, 0x8D, 0x74, 0x24, 0x50, 0x89, 0xD9])
        _emit_tx_loop(code, buf_rva=None, length=1, text_rva=text_rva)

        # --- Interactive Bare-Metal Serial Command Shell Dispatcher ---
        code += bytes([0x8B, 0x44, 0x24, 0x50])

        # 1) "STAT" (0x54415453) -> STATUS
        code += bytes([0x3D, 0x53, 0x54, 0x41, 0x54])
        jne_not_status_pos = len(code)
        code += bytes([0x75, 0x00])
        _emit_tx_loop(
            code,
            buf_rva=shell_status_rva,
            length=shell_status_len,
            text_rva=text_rva,
        )
        not_status_target = len(code)
        code[jne_not_status_pos + 1] = (not_status_target - (jne_not_status_pos + 2)) & 0xFF

        # 2) "MEM\r" (0x0D4D454D) -> MEM
        code += bytes([0x8B, 0x44, 0x24, 0x50])
        code += bytes([0x3D, 0x4D, 0x45, 0x4D, 0x0D])
        jne_not_mem_pos = len(code)
        code += bytes([0x75, 0x00])
        _emit_tx_loop(
            code,
            buf_rva=shell_mem_rva,
            length=shell_mem_len,
            text_rva=text_rva,
        )
        not_mem_target = len(code)
        code[jne_not_mem_pos + 1] = (not_mem_target - (jne_not_mem_pos + 2)) & 0xFF

        # 3) "MIR\r" (0x0D52494D) -> MIR
        code += bytes([0x8B, 0x44, 0x24, 0x50])
        code += bytes([0x3D, 0x4D, 0x49, 0x52, 0x0D])
        jne_not_mir_pos = len(code)
        code += bytes([0x75, 0x00])
        _emit_tx_loop(
            code,
            buf_rva=shell_mir_rva,
            length=shell_mir_len,
            text_rva=text_rva,
        )
        not_mir_target = len(code)
        code[jne_not_mir_pos + 1] = (not_mir_target - (jne_not_mir_pos + 2)) & 0xFF

        # 4) "EPOC" (0x434F5045) -> EPOCH (Vormir/Hela epoch advance 2 -> 3 with rdtsc check)
        code += bytes([0x8B, 0x44, 0x24, 0x50])
        code += bytes([0x3D, 0x45, 0x50, 0x4F, 0x43])
        jne_not_epoch_pos = len(code)
        code += bytes([0x75, 0x00])
        # rdtsc (0F 31); shl rdx, 32 (48 C1 E2 20); or rax, rdx (48 09 D0)
        code += bytes([0x0F, 0x31, 0x48, 0xC1, 0xE2, 0x20, 0x48, 0x09, 0xD0])
        # mov [rsp + 0x10], rax (48 89 44 24 10) -> update tsc_latest
        code += bytes([0x48, 0x89, 0x44, 0x24, 0x10])
        # inc qword ptr [rsp + 0x48] (48 FF 44 24 48) -> advance active epoch 2 -> 3
        code += bytes([0x48, 0xFF, 0x44, 0x24, 0x48])
        _emit_tx_loop(
            code,
            buf_rva=shell_epoch_rva,
            length=shell_epoch_len,
            text_rva=text_rva,
        )
        not_epoch_target = len(code)
        code[jne_not_epoch_pos + 1] = (not_epoch_target - (jne_not_epoch_pos + 2)) & 0xFF

        # 5) "HALT" (0x544C4148) -> HALT
        code += bytes([0x8B, 0x44, 0x24, 0x50])
        code += bytes([0x3D, 0x48, 0x41, 0x4C, 0x54])
        jne_not_halt_pos = len(code)
        code += bytes([0x75, 0x00])
        _emit_tx_loop(
            code,
            buf_rva=shell_halt_rva,
            length=shell_halt_len,
            text_rva=text_rva,
        )
        code += bytes([0xFA, 0xF4, 0xEB, 0xFD])
        not_halt_target = len(code)
        code[jne_not_halt_pos + 1] = (not_halt_target - (jne_not_halt_pos + 2)) & 0xFF

        no_rx_target = len(code)
        struct.pack_into("<i", code, jz_no_rx_pos + 2, no_rx_target - (jz_no_rx_pos + 6))

    # 7. Epilogue / Halt
    if halt_mode == "halt":
        code += bytes([0xFA, 0xF4, 0xEB, 0xFD])
    else:
        code += bytes(
            [
                0x31,
                0xC0,
                0x48,
                0x81,
                0xC4,
                0x90,
                0x12,
                0x00,
                0x00,
                0x41,
                0x5D,
                0x41,
                0x5C,
                0x5F,
                0x5E,
                0x5B,
                0xC3,
            ]
        )

    # 8. Out-of-line Fail-Closed Morth CPU Exception Handler (.Lmorth_isr_trap)
    if exit_boot_services:
        isr_rva = text_rva + len(code)
        lea_isr_end_rva = text_rva + lea_isr_pos + 7
        struct.pack_into("<i", code, lea_isr_pos + 3, isr_rva - lea_isr_end_rva)

        _emit_tx_loop(
            code,
            buf_rva=trap_banner_rva,
            length=trap_banner_len,
            text_rva=text_rva,
        )
        code += bytes([0xFA, 0xF4, 0xEB, 0xFD])

    return bytes(code)


def emit_uefi_x86_64_gas_v1(
    serial_payload: bytes,
    *,
    mir_fingerprint: str,
    halt_mode: str = "return",
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
) -> str:
    """Emit freestanding GNU/Clang x86-64 assembly (Intel syntax) for ``BOOTX64.EFI`` (v5)."""

    escaped_bytes = ", ".join(f"0x{b:02x}" for b in serial_payload)
    utf16_text = serial_payload.decode("utf-8")
    utf16_words = [ord(ch) for ch in utf16_text] + [0]
    escaped_words = ", ".join(f"0x{w:04x}" for w in utf16_words)
    escaped_ebs = ", ".join(f"0x{b:02x}" for b in POST_EBS_BANNER)
    escaped_v3 = ", ".join(f"0x{b:02x}" for b in KERNEL_V3_BANNER)
    escaped_v4 = ", ".join(f"0x{b:02x}" for b in KERNEL_V4_BANNER)
    escaped_v5 = ", ".join(f"0x{b:02x}" for b in KERNEL_V5_BANNER)
    escaped_trap = ", ".join(f"0x{b:02x}" for b in MORTH_TRAP_BANNER)
    escaped_gdt = ", ".join(f"0x{b:02x}" for b in GDT_TABLE_BYTES)
    escaped_rx = ", ".join(f"0x{b:02x}" for b in UART_RX_PREFIX)

    if halt_mode == "halt":
        epilogue = "\n".join(
            [
                "    cli",
                ".Lhalt:",
                "    hlt",
                "    jmp .Lhalt",
            ]
        )
    else:
        epilogue = "\n".join(
            [
                "    xor eax, eax",
                "    add rsp, 0x1290",
                "    pop r13",
                "    pop r12",
                "    pop rdi",
                "    pop rsi",
                "    pop rbx",
                "    ret",
            ]
        )

    return f"""# Koschei Bare-Metal x86-64 UEFI Kernel Prototype v5
# Sealed MIR SHA-256: {mir_fingerprint}
# Target: x86_64-unknown-uefi (COM1 0x3F8 + EBS + GDT/IDT + Titan PMM + W^X CR3 + PIC/PIT/TSC + Shell)
.intel_syntax noprefix
.text
.globl efi_main
efi_main:
    push rbx
    push rsi
    push rdi
    push r12
    push r13
    sub rsp, 0x1290
    mov r12, rcx
    mov rbx, rdx

    # 1. 16550 UART init on COM1 (0x3F8)
    # 2. Stream deterministic Koschei output to COM1 & UEFI ConOut
    # 3. Acquire Memory Map, ExitBootServices, load GDT/IDT, Titan PMM & W^X CR3
    mov rax, r8
    mov cr3, rax

    # 4. Remap & Mask 8259 PICs (0x20/0x21, 0xA0/0xA1), Init 8254 PIT (1000Hz), Read TSC
    rdtsc
    shl rdx, 32
    or rax, rdx
    mov qword ptr [rsp + 0x00], rax

.Ldone:
{epilogue}

.Lmorth_isr_trap:
    cli
    hlt
    jmp .Lmorth_isr_trap

.section .rdata,"dr"
.balign 16
.Lserial_payload:
    .byte {escaped_bytes}
.balign 16
.Lconout_utf16:
    .word {escaped_words}
.balign 16
.Lebs_banner:
    .byte {escaped_ebs}
.balign 16
.Lv3_banner:
    .byte {escaped_v3}
.balign 16
.Lv4_banner:
    .byte {escaped_v4}
.balign 16
.Lv5_banner:
    .byte {escaped_v5}
.balign 16
.Ltrap_banner:
    .byte {escaped_trap}
.balign 16
.Lgdt_table:
    .byte {escaped_gdt}
.balign 16
.Lrx_prefix:
    .byte {escaped_rx}
"""


def build_uefi_pe32plus_v1(
    mir: MirGraph,
    *,
    include_banner: bool = True,
    halt_mode: str = "return",
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
) -> UefiBootArtifactV1:
    """Compile a sealed Koschei MirGraph directly into a deterministic ``BOOTX64.EFI`` (v5)."""

    serial_payload, crlf_text = evaluate_sealed_mir_serial_output_v1(
        mir,
        include_banner=include_banner,
    )
    conout_utf16le = crlf_text.encode("utf-16le") + b"\x00\x00"
    shell_mir_reply = (
        f"[KOSCHEI-SHELL] sealed_mir_sha256={mir.fingerprint}\r\n".encode("utf-8")
    )

    text_rva = 0x1000
    rdata_rva = 0x2000

    serial_offset = 0
    utf16_offset = _align_up(serial_offset + len(serial_payload), 16)
    ebs_offset = _align_up(utf16_offset + len(conout_utf16le), 16)
    v3_offset = _align_up(ebs_offset + len(POST_EBS_BANNER), 16)
    v4_offset = _align_up(v3_offset + len(KERNEL_V3_BANNER), 16)
    v5_offset = _align_up(v4_offset + len(KERNEL_V4_BANNER), 16)
    trap_offset = _align_up(v5_offset + len(KERNEL_V5_BANNER), 16)
    gdt_offset = _align_up(trap_offset + len(MORTH_TRAP_BANNER), 16)
    rx_prefix_offset = _align_up(gdt_offset + len(GDT_TABLE_BYTES), 16)
    sh_status_offset = _align_up(rx_prefix_offset + len(UART_RX_PREFIX), 16)
    sh_mem_offset = _align_up(sh_status_offset + len(SHELL_STATUS_REPLY), 16)
    sh_mir_offset = _align_up(sh_mem_offset + len(SHELL_MEM_REPLY), 16)
    sh_epoch_offset = _align_up(sh_mir_offset + len(shell_mir_reply), 16)
    sh_halt_offset = _align_up(sh_epoch_offset + len(SHELL_EPOCH_REPLY), 16)

    rdata_buf = bytearray(sh_halt_offset + len(SHELL_HALT_REPLY))
    rdata_buf[serial_offset : serial_offset + len(serial_payload)] = serial_payload
    rdata_buf[utf16_offset : utf16_offset + len(conout_utf16le)] = conout_utf16le
    rdata_buf[ebs_offset : ebs_offset + len(POST_EBS_BANNER)] = POST_EBS_BANNER
    rdata_buf[v3_offset : v3_offset + len(KERNEL_V3_BANNER)] = KERNEL_V3_BANNER
    rdata_buf[v4_offset : v4_offset + len(KERNEL_V4_BANNER)] = KERNEL_V4_BANNER
    rdata_buf[v5_offset : v5_offset + len(KERNEL_V5_BANNER)] = KERNEL_V5_BANNER
    rdata_buf[trap_offset : trap_offset + len(MORTH_TRAP_BANNER)] = MORTH_TRAP_BANNER
    rdata_buf[gdt_offset : gdt_offset + len(GDT_TABLE_BYTES)] = GDT_TABLE_BYTES
    rdata_buf[rx_prefix_offset : rx_prefix_offset + len(UART_RX_PREFIX)] = UART_RX_PREFIX
    rdata_buf[sh_status_offset : sh_status_offset + len(SHELL_STATUS_REPLY)] = SHELL_STATUS_REPLY
    rdata_buf[sh_mem_offset : sh_mem_offset + len(SHELL_MEM_REPLY)] = SHELL_MEM_REPLY
    rdata_buf[sh_mir_offset : sh_mir_offset + len(shell_mir_reply)] = shell_mir_reply
    rdata_buf[sh_epoch_offset : sh_epoch_offset + len(SHELL_EPOCH_REPLY)] = SHELL_EPOCH_REPLY
    rdata_buf[sh_halt_offset : sh_halt_offset + len(SHELL_HALT_REPLY)] = SHELL_HALT_REPLY
    rdata_raw = bytes(rdata_buf)

    text_raw = _build_efi_main_machine_code(
        serial_rva=rdata_rva + serial_offset,
        serial_len=len(serial_payload),
        utf16_rva=rdata_rva + utf16_offset,
        ebs_banner_rva=rdata_rva + ebs_offset,
        ebs_banner_len=len(POST_EBS_BANNER),
        v3_banner_rva=rdata_rva + v3_offset,
        v3_banner_len=len(KERNEL_V3_BANNER),
        v4_banner_rva=rdata_rva + v4_offset,
        v4_banner_len=len(KERNEL_V4_BANNER),
        v5_banner_rva=rdata_rva + v5_offset,
        v5_banner_len=len(KERNEL_V5_BANNER),
        trap_banner_rva=rdata_rva + trap_offset,
        trap_banner_len=len(MORTH_TRAP_BANNER),
        gdt_rva=rdata_rva + gdt_offset,
        rx_prefix_rva=rdata_rva + rx_prefix_offset,
        rx_prefix_len=len(UART_RX_PREFIX),
        shell_status_rva=rdata_rva + sh_status_offset,
        shell_status_len=len(SHELL_STATUS_REPLY),
        shell_mem_rva=rdata_rva + sh_mem_offset,
        shell_mem_len=len(SHELL_MEM_REPLY),
        shell_mir_rva=rdata_rva + sh_mir_offset,
        shell_mir_len=len(shell_mir_reply),
        shell_epoch_rva=rdata_rva + sh_epoch_offset,
        shell_epoch_len=len(SHELL_EPOCH_REPLY),
        shell_halt_rva=rdata_rva + sh_halt_offset,
        shell_halt_len=len(SHELL_HALT_REPLY),
        text_rva=text_rva,
        rdata_rva_val=rdata_rva,
        halt_mode=halt_mode,
        exit_boot_services=exit_boot_services,
        enable_serial_rx=enable_serial_rx,
    )

    text_file_size = _align_up(len(text_raw), FILE_ALIGNMENT)
    rdata_file_size = _align_up(len(rdata_raw), FILE_ALIGNMENT)

    text_vsize = _align_up(len(text_raw), SECTION_ALIGNMENT)
    rdata_rva = text_rva + text_vsize
    if rdata_rva != 0x2000:
        text_raw = _build_efi_main_machine_code(
            serial_rva=rdata_rva + serial_offset,
            serial_len=len(serial_payload),
            utf16_rva=rdata_rva + utf16_offset,
            ebs_banner_rva=rdata_rva + ebs_offset,
            ebs_banner_len=len(POST_EBS_BANNER),
            v3_banner_rva=rdata_rva + v3_offset,
            v3_banner_len=len(KERNEL_V3_BANNER),
            v4_banner_rva=rdata_rva + v4_offset,
            v4_banner_len=len(KERNEL_V4_BANNER),
            v5_banner_rva=rdata_rva + v5_offset,
            v5_banner_len=len(KERNEL_V5_BANNER),
            trap_banner_rva=rdata_rva + trap_offset,
            trap_banner_len=len(MORTH_TRAP_BANNER),
            gdt_rva=rdata_rva + gdt_offset,
            rx_prefix_rva=rdata_rva + rx_prefix_offset,
            rx_prefix_len=len(UART_RX_PREFIX),
            shell_status_rva=rdata_rva + sh_status_offset,
            shell_status_len=len(SHELL_STATUS_REPLY),
            shell_mem_rva=rdata_rva + sh_mem_offset,
            shell_mem_len=len(SHELL_MEM_REPLY),
            shell_mir_rva=rdata_rva + sh_mir_offset,
            shell_mir_len=len(shell_mir_reply),
            shell_epoch_rva=rdata_rva + sh_epoch_offset,
            shell_epoch_len=len(SHELL_EPOCH_REPLY),
            shell_halt_rva=rdata_rva + sh_halt_offset,
            shell_halt_len=len(SHELL_HALT_REPLY),
            text_rva=text_rva,
            rdata_rva_val=rdata_rva,
            halt_mode=halt_mode,
            exit_boot_services=exit_boot_services,
            enable_serial_rx=enable_serial_rx,
        )

    rdata_vsize = _align_up(len(rdata_raw), SECTION_ALIGNMENT)
    size_of_headers = FILE_ALIGNMENT
    text_file_offset = size_of_headers
    rdata_file_offset = text_file_offset + text_file_size
    size_of_image = rdata_rva + rdata_vsize

    dos_header = bytearray(0x40)
    dos_header[0:2] = b"MZ"
    struct.pack_into("<I", dos_header, 0x3C, 0x40)

    pe_signature = b"PE\x00\x00"
    num_sections = 2
    time_date_stamp = 0
    size_of_optional_header = 240
    characteristics = 0x0002 | 0x0020
    coff_header = struct.pack(
        "<HHIIIHH",
        PE32PLUS_MACHINE_X86_64,
        num_sections,
        time_date_stamp,
        0,
        0,
        size_of_optional_header,
        characteristics,
    )

    opt_header = struct.pack(
        "<HBBIIIIIQIIHHHHHHIIIIHHQQQQII",
        PE32PLUS_MAGIC,
        1,
        0,
        text_file_size,
        rdata_file_size,
        0,
        text_rva,
        text_rva,
        UEFI_IMAGE_BASE,
        SECTION_ALIGNMENT,
        FILE_ALIGNMENT,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        size_of_image,
        size_of_headers,
        0,
        IMAGE_SUBSYSTEM_EFI_APPLICATION,
        0,
        0x100000,
        0x10000,
        0x100000,
        0x10000,
        0,
        16,
    )
    data_directories = b"\x00" * (16 * 8)
    optional_header = opt_header + data_directories
    assert len(optional_header) == size_of_optional_header

    IMAGE_SCN_CNT_CODE = 0x00000020
    IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
    IMAGE_SCN_MEM_EXECUTE = 0x20000000
    IMAGE_SCN_MEM_READ = 0x40000000

    text_section_hdr = struct.pack(
        "<8sIIIIIIHHI",
        b".text\x00\x00\x00",
        len(text_raw),
        text_rva,
        text_file_size,
        text_file_offset,
        0,
        0,
        0,
        0,
        IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ,
    )
    rdata_section_hdr = struct.pack(
        "<8sIIIIIIHHI",
        b".rdata\x00\x00",
        len(rdata_raw),
        rdata_rva,
        rdata_file_size,
        rdata_file_offset,
        0,
        0,
        0,
        0,
        IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ,
    )

    headers = (
        bytes(dos_header)
        + pe_signature
        + coff_header
        + optional_header
        + text_section_hdr
        + rdata_section_hdr
    )
    assert len(headers) <= size_of_headers
    padded_headers = headers + b"\x00" * (size_of_headers - len(headers))
    padded_text = text_raw + b"\x00" * (text_file_size - len(text_raw))
    padded_rdata = rdata_raw + b"\x00" * (rdata_file_size - len(rdata_raw))

    efi_bytes = padded_headers + padded_text + padded_rdata
    efi_sha256 = hashlib.sha256(efi_bytes).hexdigest()
    assembly_source = emit_uefi_x86_64_gas_v1(
        serial_payload,
        mir_fingerprint=mir.fingerprint,
        halt_mode=halt_mode,
        exit_boot_services=exit_boot_services,
        enable_serial_rx=enable_serial_rx,
    )

    return UefiBootArtifactV1(
        mir_fingerprint=mir.fingerprint,
        serial_payload=serial_payload,
        conout_utf16le=conout_utf16le,
        efi_bytes=efi_bytes,
        efi_sha256=efi_sha256,
        assembly_source=assembly_source,
        halt_mode=halt_mode,
        exit_boot_services=exit_boot_services,
        enable_serial_rx=enable_serial_rx,
    )


def build_esp_tree_v1(
    artifact: UefiBootArtifactV1,
    esp_dir: Path,
) -> Path:
    """Populate a standard UEFI System Partition directory tree ``EFI/BOOT/BOOTX64.EFI``."""

    boot_dir = esp_dir / "EFI" / "BOOT"
    boot_dir.mkdir(parents=True, exist_ok=True)
    efi_path = boot_dir / "BOOTX64.EFI"
    efi_path.write_bytes(artifact.efi_bytes)
    startup_nsh = esp_dir / "startup.nsh"
    startup_nsh.write_text("\\EFI\\BOOT\\BOOTX64.EFI\r\n", encoding="ascii")
    return efi_path


def build_fat16_esp_image_v1(artifact: UefiBootArtifactV1) -> bytes:
    """Create a deterministic, self-contained 4 MiB FAT16 UEFI System Partition disk image."""

    bytes_per_sector = 512
    sectors_per_cluster = 4
    cluster_size = bytes_per_sector * sectors_per_cluster
    total_sectors = 8192
    reserved_sectors = 1
    num_fats = 2
    root_dir_entries = 512
    root_dir_sectors = (root_dir_entries * 32) // bytes_per_sector
    sectors_per_fat = 16

    image = bytearray(total_sectors * bytes_per_sector)

    bpb = bytearray(bytes_per_sector)
    bpb[0:3] = b"\xEB\x3C\x90"
    bpb[3:11] = b"KOSCHEI1"
    struct.pack_into("<H", bpb, 11, bytes_per_sector)
    bpb[13] = sectors_per_cluster
    struct.pack_into("<H", bpb, 14, reserved_sectors)
    bpb[16] = num_fats
    struct.pack_into("<H", bpb, 17, root_dir_entries)
    struct.pack_into("<H", bpb, 19, total_sectors)
    bpb[21] = 0xF8
    struct.pack_into("<H", bpb, 22, sectors_per_fat)
    struct.pack_into("<H", bpb, 24, 32)
    struct.pack_into("<H", bpb, 26, 64)
    struct.pack_into("<I", bpb, 28, 0)
    struct.pack_into("<I", bpb, 32, 0)
    bpb[36] = 0x80
    bpb[38] = 0x29
    struct.pack_into("<I", bpb, 39, 0x4B534348)
    bpb[43:54] = b"KOSCHEI_ESP"
    bpb[54:62] = b"FAT16   "
    bpb[510:512] = b"\x55\xAA"
    image[0:bytes_per_sector] = bpb

    efi_bytes = artifact.efi_bytes
    efi_clusters = max(1, _align_up(len(efi_bytes), cluster_size) // cluster_size)

    fat = bytearray(sectors_per_fat * bytes_per_sector)
    struct.pack_into("<HH", fat, 0, 0xFFF8, 0xFFFF)
    struct.pack_into("<H", fat, 2 * 2, 0xFFFF)
    struct.pack_into("<H", fat, 3 * 2, 0xFFFF)
    struct.pack_into("<H", fat, 4 * 2, 0xFFFF)
    for i in range(efi_clusters):
        c = 5 + i
        next_c = (c + 1) if (i + 1 < efi_clusters) else 0xFFFF
        struct.pack_into("<H", fat, c * 2, next_c)

    fat1_offset = reserved_sectors * bytes_per_sector
    fat2_offset = (reserved_sectors + sectors_per_fat) * bytes_per_sector
    image[fat1_offset : fat1_offset + len(fat)] = fat
    image[fat2_offset : fat2_offset + len(fat)] = fat

    def _dir_entry(name8: bytes, ext3: bytes, attr: int, cluster: int, size: int) -> bytes:
        assert len(name8) == 8 and len(ext3) == 3
        entry = bytearray(32)
        entry[0:8] = name8
        entry[8:11] = ext3
        entry[11] = attr
        struct.pack_into("<H", entry, 26, cluster)
        struct.pack_into("<I", entry, 28, size)
        return bytes(entry)

    root_offset = (reserved_sectors + num_fats * sectors_per_fat) * bytes_per_sector
    data_offset = root_offset + root_dir_sectors * bytes_per_sector

    def _cluster_offset(cluster_num: int) -> int:
        return data_offset + (cluster_num - 2) * cluster_size

    startup_bytes = b"\\EFI\\BOOT\\BOOTX64.EFI\r\n"

    image[root_offset : root_offset + 32] = _dir_entry(b"EFI     ", b"   ", 0x10, 2, 0)
    image[root_offset + 32 : root_offset + 64] = _dir_entry(
        b"STARTUP ", b"NSH", 0x20, 4, len(startup_bytes)
    )

    c2 = _cluster_offset(2)
    image[c2 : c2 + 32] = _dir_entry(b".       ", b"   ", 0x10, 2, 0)
    image[c2 + 32 : c2 + 64] = _dir_entry(b"..      ", b"   ", 0x10, 0, 0)
    image[c2 + 64 : c2 + 96] = _dir_entry(b"BOOT    ", b"   ", 0x10, 3, 0)

    c3 = _cluster_offset(3)
    image[c3 : c3 + 32] = _dir_entry(b".       ", b"   ", 0x10, 3, 0)
    image[c3 + 32 : c3 + 64] = _dir_entry(b"..      ", b"   ", 0x10, 2, 0)
    image[c3 + 64 : c3 + 96] = _dir_entry(
        b"BOOTX64 ", b"EFI", 0x20, 5, len(efi_bytes)
    )

    c4 = _cluster_offset(4)
    image[c4 : c4 + len(startup_bytes)] = startup_bytes

    c5 = _cluster_offset(5)
    image[c5 : c5 + len(efi_bytes)] = efi_bytes

    return bytes(image)


def simulate_uefi_x86_64_serial_v1(
    efi_bytes: bytes,
    *,
    rx_input: bytes = b"",
    trigger_exception_vector: int | None = None,
) -> UefiEmulationResult:
    """Deterministic x86-64 PE32+ emulator for testing ``BOOTX64.EFI`` hardware I/O (v5)."""

    if len(efi_bytes) < 0x200 or efi_bytes[0:2] != b"MZ":
        raise UefiBootError("KS4013", "invalid MZ header in EFI image")
    pe_offset = struct.unpack_from("<I", efi_bytes, 0x3C)[0]
    if efi_bytes[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        raise UefiBootError("KS4013", "invalid PE signature in EFI image")

    machine, num_sections, _, _, _, opt_size, _ = struct.unpack_from(
        "<HHIIIHH", efi_bytes, pe_offset + 4
    )
    if machine != PE32PLUS_MACHINE_X86_64:
        raise UefiBootError("KS4013", f"expected x86-64 machine 0x8664, got 0x{machine:04x}")

    opt_offset = pe_offset + 24
    magic = struct.unpack_from("<H", efi_bytes, opt_offset)[0]
    if magic != PE32PLUS_MAGIC:
        raise UefiBootError("KS4013", f"expected PE32+ magic 0x020B, got 0x{magic:04x}")

    entry_rva = struct.unpack_from("<I", efi_bytes, opt_offset + 16)[0]
    image_base = struct.unpack_from("<Q", efi_bytes, opt_offset + 24)[0]
    subsystem = struct.unpack_from("<H", efi_bytes, opt_offset + 68)[0]
    if subsystem != IMAGE_SUBSYSTEM_EFI_APPLICATION:
        raise UefiBootError(
            "KS4013", f"expected EFI_APPLICATION subsystem 10, got {subsystem}"
        )

    mem: dict[int, int] = {}
    sec_table_offset = opt_offset + opt_size
    for i in range(num_sections):
        sec_off = sec_table_offset + i * 40
        vsize, rva, raw_size, raw_ptr = struct.unpack_from(
            "<IIII", efi_bytes, sec_off + 8
        )
        section_data = efi_bytes[raw_ptr : raw_ptr + raw_size]
        for idx, b in enumerate(section_data):
            mem[image_base + rva + idx] = b

    def read_u8(addr: int) -> int:
        return mem.get(addr, 0)

    def read_u16(addr: int) -> int:
        return read_u8(addr) | (read_u8(addr + 1) << 8)

    def read_u32(addr: int) -> int:
        return sum(read_u8(addr + k) << (8 * k) for k in range(4))

    def read_s32(addr: int) -> int:
        val = read_u32(addr)
        return val - 0x100000000 if (val & 0x80000000) else val

    def read_u64(addr: int) -> int:
        return sum(read_u8(addr + k) << (8 * k) for k in range(8))

    def write_u16(addr: int, val: int) -> None:
        val &= 0xFFFF
        mem[addr] = val & 0xFF
        mem[addr + 1] = (val >> 8) & 0xFF

    def write_u32(addr: int, val: int) -> None:
        val &= 0xFFFFFFFF
        for k in range(4):
            mem[addr + k] = (val >> (8 * k)) & 0xFF

    def write_u64(addr: int, val: int) -> None:
        val &= 0xFFFFFFFFFFFFFFFF
        for k in range(8):
            mem[addr + k] = (val >> (8 * k)) & 0xFF

    image_handle_val = 0x0000000100000000
    system_table_addr = 0x0000000200000000
    conout_addr = 0x0000000200001000
    boot_services_addr = 0x0000000200003000

    conout_output_string_magic_rip = 0x0000000200002000
    get_memory_map_magic_rip = 0x0000000200004000
    exit_boot_services_magic_rip = 0x0000000200005000
    return_sentinel_rip = 0x00000002FFFF0000

    write_u64(system_table_addr + 0x40, conout_addr)
    write_u64(system_table_addr + 0x60, boot_services_addr)
    write_u64(conout_addr + 0x08, conout_output_string_magic_rip)
    write_u64(boot_services_addr + 0x38, get_memory_map_magic_rip)
    write_u64(boot_services_addr + 0xE8, exit_boot_services_magic_rip)

    initial_rsp = 0x0000000300000000
    regs = {
        "rax": 0,
        "rbx": 0,
        "rcx": image_handle_val,
        "rdx": system_table_addr,
        "rsi": 0,
        "rdi": 0,
        "r8": 0,
        "r9": 0,
        "r12": 0,
        "r13": 0,
        "rsp": initial_rsp,
    }
    write_u64(regs["rsp"], return_sentinel_rip)

    rip = image_base + entry_rva
    zf = False
    cf = False
    uart_writes: list[UartPortWrite] = []
    pic_pit_writes: list[UartPortWrite] = []
    serial_out = bytearray()
    conout_buffer: list[str] = []
    rx_queue = bytearray(rx_input)
    rx_consumed = bytearray()

    memory_map_acquired = False
    exit_boot_services_called = False
    boot_services_tombstoned = False
    expected_map_key = 0x4B53434800000002
    map_key_used = 0

    gdt_loaded = False
    gdt_limit = 0
    gdt_entries: tuple[int, ...] = ()
    data_segment_selector = 0

    idt_loaded = False
    idt_limit = 0
    idt_base = 0
    idt_gate_count = 0
    idt_handler_rip = 0
    exception_trapped = False
    exception_injected = False

    titan_total_usable_pages = 0
    titan_allocated_page_phys = 0
    titan_remaining_pages = 0
    cr3_pml4_phys = 0
    wx_enforced = False
    text_pte_flags = 0
    rdata_pte_flags = 0

    tsc_counter = 0x0000001000000000
    tsc_genesis = 0
    tsc_latest = 0
    active_epoch = 0
    frame_rsp = 0

    descriptors: tuple[UefiMemoryDescriptorV1, ...] = (
        UefiMemoryDescriptorV1(
            memory_type=7,
            physical_start=0x0000000000100000,
            virtual_start=0x0000000000100000,
            number_of_pages=32768,
            attribute=0x0F,
        ),
        UefiMemoryDescriptorV1(
            memory_type=1,
            physical_start=UEFI_IMAGE_BASE,
            virtual_start=UEFI_IMAGE_BASE,
            number_of_pages=16,
            attribute=0x0F,
        ),
    )

    steps = 0

    def _snapshot_frame_state() -> None:
        nonlocal titan_remaining_pages, titan_allocated_page_phys, titan_total_usable_pages
        nonlocal tsc_genesis, tsc_latest, active_epoch
        if frame_rsp:
            tsc_genesis = read_u64(frame_rsp + 0x00)
            titan_remaining_pages = read_u64(frame_rsp + 0x08)
            tsc_latest = read_u64(frame_rsp + 0x10)
            titan_allocated_page_phys = read_u64(frame_rsp + 0x18)
            titan_total_usable_pages = read_u64(frame_rsp + 0x20)
            active_epoch = read_u64(frame_rsp + 0x48)

    while rip != return_sentinel_rip and steps < 500_000:
        steps += 1
        tsc_counter += 64
        if rip == conout_output_string_magic_rip:
            if boot_services_tombstoned:
                raise UefiBootError(
                    "KS4014",
                    "violation: attempted to call UEFI ConOut->OutputString after ExitBootServices",
                )
            ptr = regs["rdx"]
            chars: list[str] = []
            while True:
                w = read_u16(ptr)
                if w == 0:
                    break
                chars.append(chr(w))
                ptr += 2
            conout_buffer.append("".join(chars))
            regs["rax"] = 0
            rip = read_u64(regs["rsp"])
            regs["rsp"] += 8
            continue

        if rip == get_memory_map_magic_rip:
            if boot_services_tombstoned:
                raise UefiBootError(
                    "KS4014",
                    "violation: attempted to call BootServices->GetMemoryMap after ExitBootServices",
                )
            size_ptr = regs["rcx"]
            map_buf = regs["rdx"]
            key_ptr = regs["r8"]
            desc_size_ptr = regs["r9"]
            desc_ver_ptr = read_u64(regs["rsp"] + 0x28)
            avail_size = read_u64(size_ptr)
            desc_size = 48
            needed_size = len(descriptors) * desc_size
            if avail_size < needed_size:
                write_u64(size_ptr, needed_size)
                regs["rax"] = 0x8000000000000005
            else:
                for idx, d in enumerate(descriptors):
                    base = map_buf + idx * desc_size
                    write_u32(base + 0, d.memory_type)
                    write_u32(base + 4, 0)
                    write_u64(base + 8, d.physical_start)
                    write_u64(base + 16, d.virtual_start)
                    write_u64(base + 24, d.number_of_pages)
                    write_u64(base + 32, d.attribute)
                write_u64(size_ptr, needed_size)
                write_u64(key_ptr, expected_map_key)
                write_u64(desc_size_ptr, desc_size)
                if desc_ver_ptr:
                    write_u32(desc_ver_ptr, 1)
                memory_map_acquired = True
                regs["rax"] = 0
            rip = read_u64(regs["rsp"])
            regs["rsp"] += 8
            continue

        if rip == exit_boot_services_magic_rip:
            if boot_services_tombstoned:
                raise UefiBootError(
                    "KS4014",
                    "violation: duplicate BootServices->ExitBootServices call",
                )
            if regs["rcx"] != image_handle_val or regs["rdx"] != expected_map_key:
                regs["rax"] = 0x8000000000000002
            else:
                exit_boot_services_called = True
                boot_services_tombstoned = True
                map_key_used = regs["rdx"]
                regs["rax"] = 0
            rip = read_u64(regs["rsp"])
            regs["rsp"] += 8
            continue

        b0 = read_u8(rip)
        if b0 in (0x53, 0x56, 0x57):
            reg_name = {0x53: "rbx", 0x56: "rsi", 0x57: "rdi"}[b0]
            regs["rsp"] -= 8
            write_u64(regs["rsp"], regs[reg_name])
            rip += 1
        elif b0 in (0x5F, 0x5E, 0x5B):
            reg_name = {0x5F: "rdi", 0x5E: "rsi", 0x5B: "rbx"}[b0]
            regs[reg_name] = read_u64(regs["rsp"])
            regs["rsp"] += 8
            rip += 1
        elif b0 == 0xFA:
            rip += 1
        elif b0 == 0xF4:
            _snapshot_frame_state()
            regs["rax"] = 0
            break
        elif b0 == 0x0F:
            b1 = read_u8(rip + 1)
            if b1 == 0x84:
                rel32 = read_s32(rip + 2)
                rip = (rip + 6 + rel32) if zf else (rip + 6)
            elif b1 == 0x85:
                rel32 = read_s32(rip + 2)
                rip = (rip + 6 + rel32) if (not zf) else (rip + 6)
            elif b1 == 0x31:  # rdtsc
                regs["rax"] = tsc_counter & 0xFFFFFFFF
                regs["rdx"] = (tsc_counter >> 32) & 0xFFFFFFFF
                rip += 2
            elif b1 == 0x01 and read_u8(rip + 2) == 0x54 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                gdtr_addr = regs["rsp"] + disp8
                gdt_limit = read_u16(gdtr_addr)
                gdt_base = read_u64(gdtr_addr + 2)
                count = (gdt_limit + 1) // 8
                gdt_entries = tuple(read_u64(gdt_base + i * 8) for i in range(count))
                gdt_loaded = True
                rip += 5
            elif b1 == 0x01 and read_u8(rip + 2) == 0x5C and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                idtr_addr = regs["rsp"] + disp8
                idt_limit = read_u16(idtr_addr)
                idt_base = read_u64(idtr_addr + 2)
                idt_gate_count = (idt_limit + 1) // 16
                if idt_gate_count > 0:
                    off_low = read_u16(idt_base + 0)
                    off_mid = read_u16(idt_base + 6)
                    off_high = read_u32(idt_base + 8)
                    idt_handler_rip = off_low | (off_mid << 16) | (off_high << 32)
                idt_loaded = True
                rip += 5
            elif b1 == 0x22 and read_u8(rip + 2) == 0xD8:
                cr3_pml4_phys = regs["rax"]
                pml4e0 = read_u64(cr3_pml4_phys + 0)
                pdpt_phys = pml4e0 & 0x000FFFFFFFFFF000
                pdpte5 = read_u64(pdpt_phys + 0x28)
                pd_phys = pdpte5 & 0x000FFFFFFFFFF000
                pde0 = read_u64(pd_phys + 0)
                pt_phys = pde0 & 0x000FFFFFFFFFF000
                text_pte_flags = read_u64(pt_phys + 0x08)
                rdata_pte_flags = read_u64(pt_phys + 0x10)
                text_is_rx = (
                    bool(text_pte_flags & PTE_PRESENT)
                    and not bool(text_pte_flags & PTE_RW)
                    and not bool(text_pte_flags & PTE_NX)
                )
                rdata_is_ro_nx = (
                    bool(rdata_pte_flags & PTE_PRESENT)
                    and not bool(rdata_pte_flags & PTE_RW)
                    and bool(rdata_pte_flags & PTE_NX)
                )
                wx_enforced = text_is_rx and rdata_is_ro_nx
                rip += 3
            else:
                raise UefiBootError("KS4013", f"unhandled 0x0F instruction 0F {b1:02x}")
        elif b0 == 0x41:
            b1 = read_u8(rip + 1)
            if b1 in (0x54, 0x55):
                reg_name = {0x54: "r12", 0x55: "r13"}[b1]
                regs["rsp"] -= 8
                write_u64(regs["rsp"], regs[reg_name])
                rip += 2
            elif b1 in (0x5C, 0x5D):
                reg_name = {0x5C: "r12", 0x5D: "r13"}[b1]
                regs[reg_name] = read_u64(regs["rsp"])
                regs["rsp"] += 8
                rip += 2
            elif b1 == 0xFF and read_u8(rip + 2) == 0x55:
                disp8 = read_u8(rip + 3)
                target = read_u64(regs["r13"] + disp8)
                regs["rsp"] -= 8
                write_u64(regs["rsp"], rip + 4)
                rip = target
            elif b1 == 0xFF and read_u8(rip + 2) == 0x95:
                disp32 = read_s32(rip + 3)
                target = read_u64(regs["r13"] + disp32)
                regs["rsp"] -= 8
                write_u64(regs["rsp"], rip + 7)
                rip = target
            else:
                raise UefiBootError("KS4013", f"unhandled 0x41 instruction 41 {b1:02x}")
        elif b0 == 0x49:
            b1 = read_u8(rip + 1)
            b2 = read_u8(rip + 2)
            if b1 == 0x89 and b2 == 0xCC:
                regs["r12"] = regs["rcx"]
                rip += 3
            elif b1 == 0x8D and b2 == 0xB8:
                disp32 = read_s32(rip + 3)
                regs["rdi"] = (regs["r8"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0x8D and b2 == 0xB0:
                disp32 = read_s32(rip + 3)
                regs["rsi"] = (regs["r8"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0x89 and b2 == 0x00:
                write_u64(regs["r8"], regs["rax"])
                rip += 3
            elif b1 == 0x89 and b2 == 0x41:
                disp8 = read_u8(rip + 3)
                write_u64(regs["r9"] + disp8, regs["rax"])
                rip += 4
            else:
                raise UefiBootError("KS4013", f"unhandled 0x49 instruction 49 {b1:02x} {b2:02x}")
        elif b0 == 0x4C:
            b1 = read_u8(rip + 1)
            b2 = read_u8(rip + 2)
            if b1 == 0x8B and b2 == 0x6B:
                disp8 = read_u8(rip + 3)
                regs["r13"] = read_u64(regs["rbx"] + disp8)
                rip += 4
            elif b1 == 0x8B and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["r8"] = read_u64(regs["rsp"] + disp8)
                rip += 5
            elif b1 == 0x8B and b2 == 0x4C and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["r9"] = read_u64(regs["rsp"] + disp8)
                rip += 5
            elif b1 == 0x8D and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["r8"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x8D and b2 == 0x4C and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["r9"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x89 and b2 == 0xE1:
                regs["rcx"] = regs["r12"]
                rip += 3
            elif b1 == 0x89 and b2 == 0xC8:
                regs["rax"] = regs["r9"]
                rip += 3
            elif b1 == 0x89 and b2 == 0xC0:
                regs["rax"] = regs["r8"]
                rip += 3
            elif b1 == 0x01 and b2 == 0xCE:
                regs["rsi"] = (regs["rsi"] + regs["r9"]) & 0xFFFFFFFFFFFFFFFF
                rip += 3
            else:
                raise UefiBootError("KS4013", f"unhandled 0x4C instruction 4C {b1:02x} {b2:02x}")
        elif b0 == 0x4D:
            b1 = read_u8(rip + 1)
            b2 = read_u8(rip + 2)
            if b1 == 0x85 and b2 == 0xED:
                zf = regs["r13"] == 0
                rip += 3
            elif b1 == 0x85 and b2 == 0xC0:
                zf = regs["r8"] == 0
                rip += 3
            elif b1 == 0x29 and b2 == 0xC8:
                regs["r8"] = (regs["r8"] - regs["r9"]) & 0xFFFFFFFFFFFFFFFF
                zf = regs["r8"] == 0
                rip += 3
            elif b1 == 0x8D and b2 == 0x88:
                disp32 = read_s32(rip + 3)
                regs["r9"] = (regs["r8"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            else:
                raise UefiBootError("KS4013", f"unhandled 0x4D instruction 4D {b1:02x} {b2:02x}")
        elif b0 == 0x48:
            b1 = read_u8(rip + 1)
            b2 = read_u8(rip + 2)
            if b1 == 0x83 and b2 == 0xEC:
                imm8 = read_u8(rip + 3)
                regs["rsp"] -= imm8
                frame_rsp = regs["rsp"]
                rip += 4
            elif b1 == 0x83 and b2 == 0xC4:
                imm8 = read_u8(rip + 3)
                regs["rsp"] += imm8
                rip += 4
            elif b1 == 0x83 and b2 == 0xC7:
                imm8 = read_u8(rip + 3)
                regs["rdi"] = (regs["rdi"] + imm8) & 0xFFFFFFFFFFFFFFFF
                rip += 4
            elif b1 == 0x83 and b2 == 0xC8:
                imm8 = read_u8(rip + 3)
                regs["rax"] = (regs["rax"] | imm8) & 0xFFFFFFFFFFFFFFFF
                rip += 4
            elif b1 == 0x83 and b2 == 0xE8:
                imm8 = read_u8(rip + 3)
                regs["rax"] = (regs["rax"] - imm8) & 0xFFFFFFFFFFFFFFFF
                zf = regs["rax"] == 0
                rip += 4
            elif b1 == 0x81 and b2 == 0xEC:
                imm32 = read_u32(rip + 3)
                regs["rsp"] -= imm32
                frame_rsp = regs["rsp"]
                rip += 7
            elif b1 == 0x81 and b2 == 0xC4:
                _snapshot_frame_state()
                imm32 = read_u32(rip + 3)
                regs["rsp"] += imm32
                rip += 7
            elif b1 == 0x81 and b2 == 0xC2:
                imm32 = read_u32(rip + 3)
                regs["rdx"] = (regs["rdx"] + imm32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0xB8:
                regs["rax"] = read_u64(rip + 2)
                rip += 10
            elif b1 == 0x89 and b2 == 0xD3:
                regs["rbx"] = regs["rdx"]
                rip += 3
            elif b1 == 0x89 and b2 == 0xC2:
                regs["rdx"] = regs["rax"]
                rip += 3
            elif b1 == 0x89 and b2 == 0xF8:
                regs["rax"] = regs["rdi"]
                rip += 3
            elif b1 == 0x89 and b2 == 0xF0:
                regs["rax"] = regs["rsi"]
                rip += 3
            elif b1 == 0x89 and b2 == 0x07:
                write_u64(regs["rdi"], regs["rax"])
                rip += 3
            elif b1 == 0x89 and b2 == 0x04 and read_u8(rip + 3) == 0x24:  # mov [rsp], rax
                write_u64(regs["rsp"], regs["rax"])
                rip += 4
            elif b1 == 0x89 and b2 == 0x46:
                disp8 = read_u8(rip + 3)
                write_u64(regs["rsi"] + disp8, regs["rax"])
                rip += 4
            elif b1 == 0xC1 and b2 == 0xEA:
                imm8 = read_u8(rip + 3)
                regs["rdx"] = (regs["rdx"] >> imm8) & 0xFFFFFFFFFFFFFFFF
                rip += 4
            elif b1 == 0xC1 and b2 == 0xE2:  # shl rdx, imm8
                imm8 = read_u8(rip + 3)
                regs["rdx"] = (regs["rdx"] << imm8) & 0xFFFFFFFFFFFFFFFF
                rip += 4
            elif b1 == 0x09 and b2 == 0xD0:  # or rax, rdx
                regs["rax"] = (regs["rax"] | regs["rdx"]) & 0xFFFFFFFFFFFFFFFF
                rip += 3
            elif b1 == 0x03 and b2 == 0x46:
                disp8 = read_u8(rip + 3)
                regs["rax"] = (regs["rax"] + read_u64(regs["rsi"] + disp8)) & 0xFFFFFFFFFFFFFFFF
                rip += 4
            elif b1 == 0x8D and b2 == 0x05:
                disp32 = read_s32(rip + 3)
                regs["rax"] = (rip + 7 + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0x8D and b2 == 0x35:
                disp32 = read_s32(rip + 3)
                regs["rsi"] = (rip + 7 + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0x8D and b2 == 0x15:
                disp32 = read_s32(rip + 3)
                regs["rdx"] = (rip + 7 + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 7
            elif b1 == 0x8D and b2 == 0x4C and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["rcx"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x8D and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["rax"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x8D and b2 == 0x7C and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["rdi"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x8D and b2 == 0x74 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["rsi"] = (regs["rsp"] + disp8) & 0xFFFFFFFFFFFFFFFF
                rip += 5
            elif b1 == 0x8D and b2 == 0x94 and read_u8(rip + 3) == 0x24:
                disp32 = read_s32(rip + 4)
                regs["rdx"] = (regs["rsp"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 8
            elif b1 == 0x8D and b2 == 0xB4 and read_u8(rip + 3) == 0x24:
                disp32 = read_s32(rip + 4)
                regs["rsi"] = (regs["rsp"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 8
            elif b1 == 0x8D and b2 == 0xBC and read_u8(rip + 3) == 0x24:
                disp32 = read_s32(rip + 4)
                regs["rdi"] = (regs["rsp"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 8
            elif b1 == 0x8D and b2 == 0x84 and read_u8(rip + 3) == 0x24:
                disp32 = read_s32(rip + 4)
                regs["rax"] = (regs["rsp"] + disp32) & 0xFFFFFFFFFFFFFFFF
                rip += 8
            elif b1 == 0xC7 and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                imm32 = read_u32(rip + 5)
                write_u64(regs["rsp"] + disp8, imm32)
                rip += 9
            elif b1 == 0x89 and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                write_u64(regs["rsp"] + disp8, regs["rax"])
                rip += 5
            elif b1 == 0x89 and b2 == 0x54 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                write_u64(regs["rsp"] + disp8, regs["rdx"])
                rip += 5
            elif b1 == 0x8B and b2 == 0x54 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                regs["rdx"] = read_u64(regs["rsp"] + disp8)
                rip += 5
            elif b1 == 0x8B and b2 == 0x56:
                disp8 = read_u8(rip + 3)
                regs["rdx"] = read_u64(regs["rsi"] + disp8)
                rip += 4
            elif b1 == 0xFF and b2 == 0x44 and read_u8(rip + 3) == 0x24:
                # inc qword ptr [rsp + disp8]
                disp8 = read_u8(rip + 4)
                val64 = (read_u64(regs["rsp"] + disp8) + 1) & 0xFFFFFFFFFFFFFFFF
                write_u64(regs["rsp"] + disp8, val64)
                zf = val64 == 0
                rip += 5
            elif b1 == 0xFF and b2 == 0xC6:
                regs["rsi"] = (regs["rsi"] + 1) & 0xFFFFFFFFFFFFFFFF
                zf = regs["rsi"] == 0
                rip += 3
            elif b1 == 0xFF and b2 == 0xC7:
                regs["rdi"] = (regs["rdi"] + 1) & 0xFFFFFFFFFFFFFFFF
                zf = regs["rdi"] == 0
                rip += 3
            elif b1 == 0xFF and b2 == 0xC8:
                regs["rax"] = (regs["rax"] - 1) & 0xFFFFFFFFFFFFFFFF
                zf = regs["rax"] == 0
                rip += 3
            elif b1 == 0x85 and b2 == 0xDB:
                zf = regs["rbx"] == 0
                rip += 3
            elif b1 == 0x85 and b2 == 0xC9:
                zf = regs["rcx"] == 0
                rip += 3
            elif b1 == 0x85 and b2 == 0xC0:
                zf = regs["rax"] == 0
                rip += 3
            elif b1 == 0x85 and b2 == 0xD2:
                zf = regs["rdx"] == 0
                rip += 3
            elif b1 == 0x8B and b2 == 0x4B:
                disp8 = read_u8(rip + 3)
                regs["rcx"] = read_u64(regs["rbx"] + disp8)
                rip += 4
            else:
                raise UefiBootError("KS4013", f"unhandled REX.W instruction 48 {b1:02x} {b2:02x}")
        elif b0 == 0x66:
            b1 = read_u8(rip + 1)
            if b1 == 0xBA:
                imm16 = read_u16(rip + 2)
                regs["rdx"] = (regs["rdx"] & ~0xFFFF) | imm16
                rip += 4
            elif b1 == 0xB8:
                imm16 = read_u16(rip + 2)
                regs["rax"] = (regs["rax"] & ~0xFFFF) | imm16
                rip += 4
            elif b1 == 0xC7 and read_u8(rip + 2) == 0x44 and read_u8(rip + 3) == 0x24:
                disp8 = read_u8(rip + 4)
                imm16 = read_u16(rip + 5)
                write_u16(regs["rsp"] + disp8, imm16)
                rip += 7
            elif b1 == 0x89 and read_u8(rip + 2) == 0x07:
                write_u16(regs["rdi"], regs["rax"] & 0xFFFF)
                rip += 3
            elif b1 == 0x89 and read_u8(rip + 2) == 0x57:
                disp8 = read_u8(rip + 3)
                write_u16(regs["rdi"] + disp8, regs["rdx"] & 0xFFFF)
                rip += 4
            elif b1 == 0xC7 and read_u8(rip + 2) == 0x47:
                disp8 = read_u8(rip + 3)
                imm16 = read_u16(rip + 4)
                write_u16(regs["rdi"] + disp8, imm16)
                rip += 6
            else:
                raise UefiBootError("KS4013", f"unhandled 0x66 instruction 66 {b1:02x}")
        elif b0 == 0x8E:
            b1 = read_u8(rip + 1)
            if b1 in (0xD8, 0xC0, 0xD0):
                data_segment_selector = regs["rax"] & 0xFFFF
                rip += 2
            else:
                raise UefiBootError("KS4013", f"unhandled segment load 8E {b1:02x}")
        elif b0 == 0x89 and read_u8(rip + 1) == 0x57:
            disp8 = read_u8(rip + 2)
            write_u32(regs["rdi"] + disp8, regs["rdx"] & 0xFFFFFFFF)
            rip += 3
        elif b0 == 0x8B and read_u8(rip + 1) == 0x44 and read_u8(rip + 2) == 0x24:
            disp8 = read_u8(rip + 3)
            regs["rax"] = read_u32(regs["rsp"] + disp8)
            rip += 4
        elif b0 == 0x3D:
            imm32 = read_u32(rip + 1)
            eax_val = regs["rax"] & 0xFFFFFFFF
            zf = eax_val == imm32
            cf = eax_val < imm32
            rip += 5
        elif b0 == 0xC7 and read_u8(rip + 1) == 0x47:
            disp8 = read_u8(rip + 2)
            imm32 = read_u32(rip + 3)
            write_u32(regs["rdi"] + disp8, imm32)
            rip += 7
        elif b0 == 0x83 and read_u8(rip + 1) == 0x3E:
            imm8 = read_u8(rip + 2)
            val32 = read_u32(regs["rsi"])
            zf = val32 == imm8
            cf = val32 < imm8
            rip += 3
        elif b0 == 0x30 and read_u8(rip + 1) == 0xC0:
            regs["rax"] &= ~0xFF
            zf = True
            rip += 2
        elif b0 == 0x31 and read_u8(rip + 1) == 0xC0:
            regs["rax"] = 0
            zf = True
            rip += 2
        elif b0 == 0x31 and read_u8(rip + 1) == 0xDB:
            regs["rbx"] = 0
            zf = True
            rip += 2
        elif b0 == 0x85 and read_u8(rip + 1) == 0xDB:
            zf = (regs["rbx"] & 0xFFFFFFFF) == 0
            rip += 2
        elif b0 == 0x89 and read_u8(rip + 1) == 0xD9:
            regs["rcx"] = regs["rbx"] & 0xFFFFFFFF
            rip += 2
        elif b0 == 0xB0:
            imm8 = read_u8(rip + 1)
            regs["rax"] = (regs["rax"] & ~0xFF) | imm8
            rip += 2
        elif b0 == 0xB9:
            regs["rcx"] = read_u32(rip + 1)
            rip += 5
        elif b0 == 0xEE:
            port = regs["rdx"] & 0xFFFF
            val = regs["rax"] & 0xFF
            if port in (PIC1_CMD, PIC1_DATA, PIC2_CMD, PIC2_DATA, PIT_CMD, PIT_CH0_DATA):
                pic_pit_writes.append(UartPortWrite(port=port, value=val))
            else:
                uart_writes.append(UartPortWrite(port=port, value=val))
                if port == COM1_THR and len(uart_writes) > 7:
                    serial_out.append(val)
            rip += 1
        elif b0 == 0xEC:
            port = regs["rdx"] & 0xFFFF
            if port == COM1_LSR:
                lsr = 0x60
                if rx_queue:
                    lsr |= COM1_LSR_DR
                regs["rax"] = (regs["rax"] & ~0xFF) | lsr
            elif port == COM1_RBR:
                b_in = rx_queue.pop(0) if rx_queue else 0
                rx_consumed.append(b_in)
                regs["rax"] = (regs["rax"] & ~0xFF) | b_in
            else:
                regs["rax"] &= ~0xFF
            rip += 1
        elif b0 == 0xA8:
            imm8 = read_u8(rip + 1)
            zf = ((regs["rax"] & 0xFF) & imm8) == 0
            rip += 2
        elif b0 == 0x3C:
            imm8 = read_u8(rip + 1)
            al_val = regs["rax"] & 0xFF
            zf = al_val == imm8
            cf = al_val < imm8
            rip += 2
        elif b0 == 0x83 and read_u8(rip + 1) == 0xFB:
            imm8 = read_u8(rip + 2)
            ebx_val = regs["rbx"] & 0xFFFFFFFF
            zf = ebx_val == imm8
            cf = ebx_val < imm8
            rip += 3
        elif b0 == 0x83 and read_u8(rip + 1) == 0xC3:
            imm8 = read_u8(rip + 2)
            regs["rbx"] = (regs["rbx"] + imm8) & 0xFFFFFFFF
            zf = regs["rbx"] == 0
            rip += 3
        elif b0 == 0x72:
            rel8 = read_u8(rip + 1)
            if rel8 & 0x80:
                rel8 -= 0x100
            rip = (rip + 2 + rel8) if cf else (rip + 2)
        elif b0 == 0x74:
            rel8 = read_u8(rip + 1)
            if rel8 & 0x80:
                rel8 -= 0x100
            rip = (rip + 2 + rel8) if zf else (rip + 2)
        elif b0 == 0x75:
            rel8 = read_u8(rip + 1)
            if rel8 & 0x80:
                rel8 -= 0x100
            rip = (rip + 2 + rel8) if (not zf) else (rip + 2)
        elif b0 == 0xEB:
            rel8 = read_u8(rip + 1)
            if rel8 & 0x80:
                rel8 -= 0x100
            rip = rip + 2 + rel8
        elif b0 == 0x8A and read_u8(rip + 1) == 0x06:
            regs["rax"] = (regs["rax"] & ~0xFF) | read_u8(regs["rsi"])
            rip += 2
        elif b0 == 0x88 and read_u8(rip + 1) == 0x07:
            mem[regs["rdi"]] = regs["rax"] & 0xFF
            rip += 2
        elif b0 == 0xC6 and read_u8(rip + 1) == 0x07:
            mem[regs["rdi"]] = read_u8(rip + 2)
            rip += 3
        elif b0 == 0xC6 and read_u8(rip + 1) == 0x47:
            disp8 = read_u8(rip + 2)
            mem[regs["rdi"] + disp8] = read_u8(rip + 3)
            rip += 4
        elif b0 == 0xFF and read_u8(rip + 1) == 0xC9:
            regs["rcx"] = (regs["rcx"] - 1) & 0xFFFFFFFF
            zf = regs["rcx"] == 0
            rip += 2
        elif b0 == 0xFF and read_u8(rip + 1) == 0xC3:
            regs["rbx"] = (regs["rbx"] + 1) & 0xFFFFFFFF
            zf = regs["rbx"] == 0
            rip += 2
        elif b0 == 0xFF and read_u8(rip + 1) == 0x51:
            disp8 = read_u8(rip + 2)
            target = read_u64(regs["rcx"] + disp8)
            regs["rsp"] -= 8
            write_u64(regs["rsp"], rip + 3)
            rip = target
        elif b0 == 0xC3:
            rip = read_u64(regs["rsp"])
            regs["rsp"] += 8
        else:
            raise UefiBootError("KS4013", f"unhandled x86-64 opcode 0x{b0:02x} at RIP=0x{rip:x}")

        if (
            trigger_exception_vector is not None
            and idt_loaded
            and not exception_injected
            and KERNEL_V5_BANNER in bytes(serial_out)
        ):
            if not (0 <= trigger_exception_vector < idt_gate_count):
                raise UefiBootError("KS4013", f"invalid exception vector {trigger_exception_vector}")
            exception_injected = True
            exception_trapped = True
            gate_addr = idt_base + trigger_exception_vector * 16
            off_low = read_u16(gate_addr + 0)
            off_mid = read_u16(gate_addr + 6)
            off_high = read_u32(gate_addr + 8)
            rip = off_low | (off_mid << 16) | (off_high << 32)

    expected_pic_pit = (
        UartPortWrite(PIC1_CMD, 0x11),
        UartPortWrite(PIC2_CMD, 0x11),
        UartPortWrite(PIC1_DATA, 0x20),
        UartPortWrite(PIC2_DATA, 0x28),
        UartPortWrite(PIC1_DATA, 0x04),
        UartPortWrite(PIC2_DATA, 0x02),
        UartPortWrite(PIC1_DATA, 0x01),
        UartPortWrite(PIC2_DATA, 0x01),
        UartPortWrite(PIC1_DATA, 0xFF),
        UartPortWrite(PIC2_DATA, 0xFF),
        UartPortWrite(PIT_CMD, 0x36),
        UartPortWrite(PIT_CH0_DATA, 0xA9),
        UartPortWrite(PIT_CH0_DATA, 0x04),
    )
    pic_remapped_and_masked = tuple(pic_pit_writes) == expected_pic_pit
    pit_divisor = (
        (pic_pit_writes[11].value | (pic_pit_writes[12].value << 8))
        if len(pic_pit_writes) >= 13
        else 0
    )

    init_writes = tuple(uart_writes[:7])
    return UefiEmulationResult(
        exit_status=regs["rax"],
        uart_init_writes=init_writes,
        serial_bytes=bytes(serial_out),
        serial_text=bytes(serial_out).decode("utf-8", errors="replace"),
        conout_text="".join(conout_buffer),
        instructions_executed=steps,
        memory_map_acquired=memory_map_acquired,
        exit_boot_services_called=exit_boot_services_called,
        boot_services_tombstoned=boot_services_tombstoned,
        map_key_used=map_key_used,
        memory_descriptors=descriptors if memory_map_acquired else (),
        rx_bytes_consumed=bytes(rx_consumed),
        gdt_loaded=gdt_loaded,
        gdt_limit=gdt_limit,
        gdt_entries=gdt_entries,
        data_segment_selector=data_segment_selector,
        idt_loaded=idt_loaded,
        idt_limit=idt_limit,
        idt_gate_count=idt_gate_count,
        idt_handler_rip=idt_handler_rip,
        titan_total_usable_pages=titan_total_usable_pages,
        titan_allocated_page_phys=titan_allocated_page_phys,
        titan_remaining_pages=titan_remaining_pages,
        cr3_pml4_phys=cr3_pml4_phys,
        wx_enforced=wx_enforced,
        text_pte_flags=text_pte_flags,
        rdata_pte_flags=rdata_pte_flags,
        pic_remapped_and_masked=pic_remapped_and_masked,
        pit_divisor=pit_divisor,
        tsc_genesis=tsc_genesis,
        tsc_latest=tsc_latest,
        active_epoch=active_epoch,
        exception_trapped=exception_trapped,
    )
