"""Koschei x86-64 UEFI boot prototype v5: COM1, ExitBootServices, GDT/IDT & Shell.

This module compiles a checked, sealed Koschei MirGraph into a freestanding
x86-64 UEFI application (``BOOTX64.EFI``, PE32+ machine ``0x8664``, subsystem
``10`` = ``IMAGE_SUBSYSTEM_EFI_APPLICATION``) that:
1. Initializes the hardware 16550 UART controller on ``COM1`` (I/O port ``0x3F8``,
   115200 baud, 8N1, 14-byte FIFO).
2. Streams the deterministic Koschei MIR boot output to ``COM1`` and mirrors it
   to ``SystemTable->ConOut->OutputString`` while UEFI BootServices are still live.
3. Reads the memory map via ``BootServices->GetMemoryMap`` (offset ``0x38``) into
   a 32 KiB buffer and calls ``BootServices->ExitBootServices(ImageHandle, MapKey)``
   (offset ``0xE8``), retrying both once with a fresh map key. A failure is
   printed with the firmware status.
4. Installs its own 64-bit Ring-0 **GDT** (``lgdt``; ``ds/es/fs/gs/ss = 0x10`` and
   ``cs = 0x08`` through a far return) and 32-vector **IDT** (``lidt``, binding
   CPU exceptions ``0..31`` to a fail-closed Morth serial trap).
5. Remaps the legacy dual **8259 PIC** controllers (``0x20/0x21``, ``0xA0/0xA1``) to
   vectors ``0x20..0x2F`` and masks every IRQ line (``0xFF``), programs the
   **8254 PIT** (``0x43/0x40``, divisor ``1193``) with interrupts still disabled,
   and samples the **TSC** (``rdtsc``) at ``epoch = 2``.
6. Serves an interactive COM1 shell (``STATUS``, ``MEM``, ``MIR``, ``EPOCH``,
   ``TRAP``, ``HALT``) and never returns to the firmware after ExitBootServices.

Every line it prints after the MIR payload carries the values the code read at
run time. Paging stays the firmware's identity mapping: there are no Koschei
page tables, no W^X and no memory isolation. ``experimental_page_tables`` adds
the unfinished Titan allocator and page-table switch (``mov cr3``), which maps
only the two link-address image pages and faults on real hardware.
``tests/test_uefi_boot_qemu_v1.py`` boots the images in QEMU with OVMF.
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
# The accessed bit is preset in both descriptors: loading a selector then never
# makes the CPU write to the descriptor, which lives in the read-only .rdata.
GDT_KERNEL_CODE64_DESC = 0x00AF9B000000FFFF  # Selector 0x08: 64-bit Ring-0 Code
GDT_KERNEL_DATA64_DESC = 0x00CF93000000FFFF  # Selector 0x10: 64-bit Ring-0 Data
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

EFI_INVALID_PARAMETER = 0x8000000000000002
EFI_BUFFER_TOO_SMALL = 0x8000000000000005

# ``efi_main`` stack frame, as offsets from ``rsp`` after the prologue. The
# first 0x20 bytes are the shadow space every UEFI call may overwrite, so
# nothing that must survive a call lives there; after ExitBootServices no call
# is made and they hold the TSC and experimental allocator values.
SLOT_TSC_GENESIS = 0x00
SLOT_PMM_REMAINING = 0x08
SLOT_TSC_LATEST = 0x10
SLOT_PMM_FIRST_PAGE = 0x18
SLOT_CALL_ARG5 = 0x20
SLOT_MAP_SIZE = 0x28
SLOT_MAP_KEY = 0x30
SLOT_DESCRIPTOR_SIZE = 0x38
SLOT_DESCRIPTOR_VERSION = 0x40
SLOT_DESCRIPTOR_TABLE = 0x48  # 10-byte GDTR/IDTR scratch, then the epoch
SLOT_EPOCH = 0x48
RX_LINE_BUFFER = 0x50  # 64 bytes
SLOT_STATUS = 0x90
SLOT_ATTEMPT = 0x98
SLOT_IMAGE_TEXT = 0xA0
MEMORY_MAP_BUFFER = 0xB0
# OVMF's map is a few KiB; 4 KiB, the old size, is too small for it.
MEMORY_MAP_BUFFER_BYTES = 0x8000
IDT_TABLE = MEMORY_MAP_BUFFER + MEMORY_MAP_BUFFER_BYTES
FRAME_BYTES = IDT_TABLE + 32 * 16

# Every line after the MIR payload states what the code did and prints the
# values it read at run time as 16 hex digits; no line is a canned claim.
POST_EBS_BANNER = b"[KOSCHEI-KERNEL-V2] ExitBootServices=OK attempt=0x"
POST_EBS_MAP_FIELD = b" memory_map_bytes=0x"
POST_EBS_DESCRIPTOR_FIELD = b" descriptor_bytes=0x"
CRLF = b"\r\n"
NO_BOOT_SERVICES_BANNER = (
    b"[KOSCHEI-KERNEL-V2] FAILED: no UEFI BootServices table; "
    b"ExitBootServices not attempted; returning EFI_INVALID_PARAMETER\r\n"
)
MEMORY_MAP_FAILED_BANNER = b"[KOSCHEI-KERNEL-V2] FAILED: GetMemoryMap status=0x"
MEMORY_MAP_NEEDED_FIELD = b" needed_bytes=0x"
MEMORY_MAP_FAILED_TAIL = (
    b"; ExitBootServices not attempted; returning the status to the firmware\r\n"
)
EXIT_FAILED_BANNER = b"[KOSCHEI-KERNEL-V2] FAILED after an ExitBootServices attempt: status=0x"
EXIT_FAILED_ATTEMPT_FIELD = b" attempt=0x"
EXIT_FAILED_TAIL = b"; boot services may be partly stopped; halting\r\n"
KERNEL_V3_BANNER = (
    b"[KOSCHEI-KERNEL-V3] gdt=loaded cs=0x08 ds=es=fs=gs=ss=0x10 "
    b"idt=32_gates(0-31 -> fail-closed trap) image_text=0x"
)
KERNEL_V4_BANNER = b"[KOSCHEI-KERNEL-V4] paging=firmware_identity own_page_tables=none\r\n"
EXPERIMENTAL_PMM_BANNER = (
    b"[KOSCHEI-KERNEL-V3X] EXPERIMENTAL page tables at first_conventional_page=0x"
)
EXPERIMENTAL_PMM_TAIL = (
    b"; they map only the two link-address image pages, not the running code, "
    b"stack or IDT\r\n"
)
EXPERIMENTAL_CR3_BANNER = (
    b"[KOSCHEI-KERNEL-V4X] EXPERIMENTAL own CR3 loaded and execution continued\r\n"
)
KERNEL_V5_BANNER = (
    b"[KOSCHEI-KERNEL-V5] pic_8259=remapped_0x20_0x28_all_masked "
    b"pit_8254=programmed_divisor_1193 interrupts=disabled tsc=0x"
)
KERNEL_V5_TAIL = b" epoch=2\r\n"
MORTH_TRAP_BANNER = (
    b"[KOSCHEI-MORTH-TRAP] cpu_exception_caught=true halting_fail_closed\r\n"
)
UART_RX_PREFIX = b"[KOSCHEI-UART-RX] recv="

SHELL_READY_BANNER = b"[KOSCHEI-SHELL] ready: STATUS, MEM, MIR, EPOCH, TRAP, HALT\r\n"
SHELL_STATUS_REPLY = (
    b"[KOSCHEI-SHELL] status=ring0 boot_services=exited gdt=0x08/0x10 "
    b"idt=32_gates paging=firmware_identity epoch=0x"
)
SHELL_STATUS_EXPERIMENTAL_REPLY = (
    b"[KOSCHEI-SHELL] status=ring0 boot_services=exited gdt=0x08/0x10 "
    b"idt=32_gates paging=experimental_own_cr3 epoch=0x"
)
SHELL_MEM_REPLY = b"[KOSCHEI-SHELL] memory_map_bytes=0x"
SHELL_MEM_DESCRIPTOR_FIELD = b" descriptor_bytes=0x"
SHELL_MEM_TAIL = b" own_page_tables=none allocator=none\r\n"
SHELL_EPOCH_REPLY = b"[KOSCHEI-SHELL] epoch=0x"
SHELL_EPOCH_TSC_FIELD = b" tsc=0x"
SHELL_HALT_REPLY = (
    b"[KOSCHEI-SHELL] halt_requested=true executing_cli_hlt\r\n"
)
# TRAP executes ud2: the CPU raises #UD (vector 6) and delivers it through the
# Koschei IDT and GDT, so a working fail-closed trap on real hardware proves
# both tables and the reloaded CS.
SHELL_TRAP_REPLY = b"[KOSCHEI-SHELL] trap_requested=true executing_ud2\r\n"
SHELL_UNKNOWN_REPLY = (
    b"[KOSCHEI-SHELL] unknown command; use STATUS, MEM, MIR, EPOCH, TRAP or HALT\r\n"
)


def hex_field(value: int) -> bytes:
    """The 16 lowercase hex digits the boot code prints for a 64-bit value."""

    return b"%016x" % (value & 0xFFFFFFFFFFFFFFFF)


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
    code_segment_selector: int = 0
    exit_boot_services_attempts: int = 0
    memory_map_bytes: int = 0
    descriptor_bytes: int = 0
    image_text_address: int = 0
    failure_status: int = 0
    triple_fault: bool = False
    waiting_for_input: bool = False
    exit_boot_services_calls: int = 0


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
    experimental_page_tables: bool = False


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
        lines.append("[KOSCHEI-UEFI-V1] sealed MIR output complete")

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


def _disp32(value: int) -> bytes:
    return struct.pack("<i", value)


def _build_efi_main_machine_code(
    *,
    strings: dict[str, tuple[int, int]],
    gdt_rva: int,
    text_rva: int,
    rdata_rva_val: int,
    halt_mode: str,
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
    experimental_page_tables: bool = False,
) -> bytes:
    """Assemble deterministic x86-64 machine code for ``efi_main`` (v5).

    ``strings`` maps each ``.rdata`` text to its RVA and length. The stack frame
    is described by the ``SLOT_*`` constants: ``sub rsp, FRAME_BYTES`` after
    five callee-saved pushes keeps ``rsp`` 16-byte aligned for UEFI calls.

    With ``exit_boot_services`` the code reads the memory map into a
    ``MEMORY_MAP_BUFFER_BYTES`` buffer and calls ExitBootServices, retrying
    both once with a fresh map key as the UEFI specification requires. A
    failure is printed with the firmware status: before any exit attempt the
    status is returned to the firmware; after a failed exit attempt the boot
    services may be partly stopped, so the code halts. After a successful exit
    it loads its own GDT (reloading CS with a far return) and IDT, programs
    and masks the PIC and PIT, prints what it read at run time and, with
    ``enable_serial_rx``, serves the COM1 shell until ``HALT``. It never
    returns to the firmware after ExitBootServices.

    ``experimental_page_tables`` additionally emits the Titan page allocator
    and a page-table switch (``mov cr3``). It maps only the two link-address
    image pages, so on real hardware the next fetch or stack access faults and
    the fault cannot be delivered; it is kept for experiments only.
    """

    if halt_mode not in ("return", "halt"):
        raise ValueError(f"unsupported halt_mode: {halt_mode!r}")
    if enable_serial_rx and not exit_boot_services:
        raise ValueError("the COM1 shell runs only after ExitBootServices")
    if experimental_page_tables and not exit_boot_services:
        raise ValueError("experimental page tables need ExitBootServices")

    code = bytearray()

    def tx(name: str) -> None:
        rva, length = strings[name]
        _emit_tx_loop(code, buf_rva=rva, length=length, text_rva=text_rva)

    def hex64(slot: int) -> None:
        # mov r8, [rsp + slot]; then 16 times: rol r8, 4; print the low nibble.
        code.extend(b"\x4C\x8B\x84\x24" + _disp32(slot))
        code.extend(b"\xB9\x10\x00\x00\x00")
        loop_top = len(code)
        code.extend(b"\x49\xC1\xC0\x04")  # rol r8, 4
        code.extend(b"\x4C\x89\xC0")  # mov rax, r8
        code.extend(b"\x24\x0F")  # and al, 0x0F
        code.extend(b"\x3C\x0A")  # cmp al, 10
        code.extend(b"\x72\x04")  # jb digit
        code.extend(b"\x04\x57")  # add al, 'a' - 10
        code.extend(b"\xEB\x02")  # jmp send
        code.extend(b"\x04\x30")  # digit: add al, '0'
        code.extend(b"\x41\x88\xC1")  # send: mov r9b, al
        poll = len(code)
        code.extend(b"\x66\xBA\xFD\x03\xEC\xA8" + bytes([COM1_LSR_THRE]))
        code.extend(bytes([0x74, (poll - (len(code) + 2)) & 0xFF]))
        code.extend(b"\x44\x88\xC8")  # mov al, r9b
        code.extend(b"\x66\xBA\xF8\x03\xEE")
        code.extend(b"\xFF\xC9")
        code.extend(bytes([0x75, (loop_top - (len(code) + 2)) & 0xFF]))

    def jump32(opcode: bytes) -> int:
        code.extend(opcode + b"\x00\x00\x00\x00")
        return len(code) - 4

    def land(field: int, target: int | None = None) -> None:
        destination = len(code) if target is None else target
        struct.pack_into("<i", code, field, destination - (field + 4))

    def store_rax(slot: int) -> None:
        code.extend(b"\x48\x89\x84\x24" + _disp32(slot))

    def store_imm(slot: int, value: int) -> None:
        code.extend(b"\x48\xC7\x84\x24" + _disp32(slot) + struct.pack("<I", value))

    def halt_forever() -> None:
        code.extend(b"\xFA\xF4\xEB\xFD")

    def epilogue_return_rax() -> None:
        code.extend(b"\x48\x81\xC4" + struct.pack("<I", FRAME_BYTES))
        code.extend(b"\x41\x5D\x41\x5C\x5F\x5E\x5B\xC3")

    # 1. Prologue: push rbx, rsi, rdi, r12, r13; sub rsp, FRAME_BYTES
    code += bytes([0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55])
    code += b"\x48\x81\xEC" + struct.pack("<I", FRAME_BYTES)
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
    tx("payload")

    # 4. Mirror output via SystemTable->ConOut->OutputString while BootServices are live
    code += bytes([0x48, 0x85, 0xDB])
    jz_skip_st_pos = len(code)
    code += bytes([0x74, 0x00])

    code += bytes([0x48, 0x8B, 0x4B, 0x40])
    code += bytes([0x48, 0x85, 0xC9])
    jz_skip_conout_pos = len(code)
    code += bytes([0x74, 0x00])

    lea_rdx_end_rva = text_rva + len(code) + 7
    disp_utf16 = strings["utf16"][0] - lea_rdx_end_rva
    code += bytes([0x48, 0x8D, 0x15]) + struct.pack("<i", disp_utf16)
    code += bytes([0xFF, 0x51, 0x08])

    skip_conout_target = len(code)
    code[jz_skip_st_pos + 1] = (skip_conout_target - (jz_skip_st_pos + 2)) & 0xFF
    code[jz_skip_conout_pos + 1] = (skip_conout_target - (jz_skip_conout_pos + 2)) & 0xFF

    if not exit_boot_services:
        # 5'. Boot services stay with the firmware: return or halt as asked.
        if halt_mode == "halt":
            halt_forever()
        else:
            code += b"\x31\xC0"
            epilogue_return_rax()
        return bytes(code)

    # 5. GetMemoryMap + ExitBootServices, each retried once with a fresh map key.
    code += bytes([0x48, 0x85, 0xDB])
    no_boot_services = [jump32(b"\x0F\x84")]
    code += bytes([0x4C, 0x8B, 0x6B, 0x60])
    code += bytes([0x4D, 0x85, 0xED])
    no_boot_services.append(jump32(b"\x0F\x84"))

    map_failed_before_exit: list[int] = []
    failed_after_exit_attempt: list[int] = []
    exit_succeeded: list[int] = []
    for attempt in (1, 2):
        store_imm(SLOT_ATTEMPT, attempt)
        code += b"\x48\xC7\x44\x24" + bytes([SLOT_MAP_SIZE]) + struct.pack("<I", MEMORY_MAP_BUFFER_BYTES)
        code += bytes([0x48, 0x8D, 0x4C, 0x24, SLOT_MAP_SIZE])
        code += b"\x48\x8D\x94\x24" + _disp32(MEMORY_MAP_BUFFER)
        code += bytes([0x4C, 0x8D, 0x44, 0x24, SLOT_MAP_KEY])
        code += bytes([0x4C, 0x8D, 0x4C, 0x24, SLOT_DESCRIPTOR_SIZE])
        code += bytes([0x48, 0x8D, 0x44, 0x24, SLOT_DESCRIPTOR_VERSION])
        code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_CALL_ARG5])
        code += bytes([0x41, 0xFF, 0x55, 0x38])  # call [r13 + GetMemoryMap]
        code += bytes([0x48, 0x85, 0xC0])
        target = map_failed_before_exit if attempt == 1 else failed_after_exit_attempt
        target.append(jump32(b"\x0F\x85"))

        code += bytes([0x4C, 0x89, 0xE1])
        code += bytes([0x48, 0x8B, 0x54, 0x24, SLOT_MAP_KEY])
        code += bytes([0x41, 0xFF, 0x95, 0xE8, 0x00, 0x00, 0x00])  # call [r13 + ExitBootServices]
        code += bytes([0x48, 0x85, 0xC0])
        if attempt == 1:
            exit_succeeded.append(jump32(b"\x0F\x84"))
        else:
            failed_after_exit_attempt.append(jump32(b"\x0F\x85"))

    for field in exit_succeeded:
        land(field)

    # The address the firmware actually loaded .text at.
    lea_end = text_rva + len(code) + 7
    code += b"\x48\x8D\x05" + _disp32(text_rva - lea_end)
    store_rax(SLOT_IMAGE_TEXT)

    tx("v2")
    hex64(SLOT_ATTEMPT)
    tx("v2_map")
    hex64(SLOT_MAP_SIZE)
    tx("v2_descriptor")
    hex64(SLOT_DESCRIPTOR_SIZE)
    tx("crlf")

    # --- STAGE 3A: Load Koschei 64-bit GDT (lgdt), reload data selectors and CS ---
    code += bytes([0xFA])  # cli
    code += bytes([0x66, 0xC7, 0x44, 0x24, SLOT_DESCRIPTOR_TABLE, 0x17, 0x00])
    lea_gdt_end_rva = text_rva + len(code) + 7
    code += bytes([0x48, 0x8D, 0x05]) + struct.pack("<i", gdt_rva - lea_gdt_end_rva)
    code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_DESCRIPTOR_TABLE + 2])
    code += bytes([0x0F, 0x01, 0x54, 0x24, SLOT_DESCRIPTOR_TABLE])  # lgdt
    code += bytes([0x66, 0xB8, 0x10, 0x00])  # mov ax, 0x10
    code += bytes([0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xE0, 0x8E, 0xE8, 0x8E, 0xD0])  # ds es fs gs ss
    # push 0x08; lea rax, [rip + 3]; push rax; retfq  -> CS = 0x08
    code += bytes([0x6A, 0x08, 0x48, 0x8D, 0x05, 0x03, 0x00, 0x00, 0x00, 0x50, 0x48, 0xCB])

    # --- STAGE 3B: Populate 32-vector 64-bit IDT & execute lidt ---
    lea_isr_pos = len(code)
    code += bytes([0x48, 0x8D, 0x05, 0x00, 0x00, 0x00, 0x00])
    code += b"\x48\x8D\xBC\x24" + _disp32(IDT_TABLE)
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

    code += bytes([0x66, 0xC7, 0x44, 0x24, SLOT_DESCRIPTOR_TABLE, 0xFF, 0x01])
    code += b"\x48\x8D\x84\x24" + _disp32(IDT_TABLE)
    code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_DESCRIPTOR_TABLE + 2])
    code += bytes([0x0F, 0x01, 0x5C, 0x24, SLOT_DESCRIPTOR_TABLE])  # lidt

    tx("v3")
    hex64(SLOT_IMAGE_TEXT)
    tx("crlf")

    if experimental_page_tables:
        # --- STAGE 3C (experimental): Titan Physical Page Frame Allocator ---
        code += b"\x48\x8D\xB4\x24" + _disp32(MEMORY_MAP_BUFFER)
        code += bytes([0x4C, 0x8B, 0x44, 0x24, SLOT_MAP_SIZE])
        code += bytes([0x4C, 0x8B, 0x4C, 0x24, SLOT_DESCRIPTOR_SIZE])
        code += bytes([0x31, 0xC0])
        code += bytes([0x48, 0xC7, 0x44, 0x24, SLOT_PMM_FIRST_PAGE, 0x00, 0x00, 0x00, 0x00])

        pmm_loop_top = len(code)
        code += bytes([0x4D, 0x85, 0xC0])
        jz_pmm_done_pos = len(code)
        code += bytes([0x74, 0x00])
        code += bytes([0x83, 0x3E, 0x07])
        jne_pmm_next_pos = len(code)
        code += bytes([0x75, 0x00])
        code += bytes([0x48, 0x03, 0x46, 0x18])
        code += bytes([0x48, 0x8B, 0x54, 0x24, SLOT_PMM_FIRST_PAGE, 0x48, 0x85, 0xD2])
        jnz_already_alloc_pos = len(code)
        code += bytes([0x75, 0x00])
        code += bytes([0x48, 0x8B, 0x56, 0x08])
        code += bytes([0x48, 0x89, 0x54, 0x24, SLOT_PMM_FIRST_PAGE])
        code += bytes([0x48, 0x81, 0xC2, 0x00, 0x40, 0x00, 0x00, 0x48, 0x89, 0x54, 0x24, SLOT_TSC_LATEST])

        pmm_next_target = len(code)
        code[jne_pmm_next_pos + 1] = (pmm_next_target - (jne_pmm_next_pos + 2)) & 0xFF
        code[jnz_already_alloc_pos + 1] = (pmm_next_target - (jnz_already_alloc_pos + 2)) & 0xFF
        code += bytes([0x4C, 0x01, 0xCE, 0x4D, 0x29, 0xC8])
        jmp_pmm_rel = pmm_loop_top - (len(code) + 2)
        code += bytes([0xEB, jmp_pmm_rel & 0xFF])

        pmm_done_target = len(code)
        code[jz_pmm_done_pos + 1] = (pmm_done_target - (jz_pmm_done_pos + 2)) & 0xFF
        code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_CALL_ARG5])
        code += bytes([0x48, 0x83, 0xE8, 0x04, 0x48, 0x89, 0x44, 0x24, SLOT_PMM_REMAINING])

        tx("v3x")
        hex64(SLOT_PMM_FIRST_PAGE)
        tx("v3x_tail")

        # --- STAGE 4A (experimental): 4-level page tables & load CR3 ---
        code += bytes([0x4C, 0x8B, 0x44, 0x24, SLOT_PMM_FIRST_PAGE])
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

        tx("v4x")
    else:
        tx("v4")

    # --- STAGE 5: Remap & Mask 8259 PICs, program the 8254 PIT, read the TSC ---
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

    # rdtsc; shl rdx, 32; or rax, rdx -> [rsp + TSC genesis] and [rsp + TSC latest]
    code += bytes([0x0F, 0x31, 0x48, 0xC1, 0xE2, 0x20, 0x48, 0x09, 0xD0])
    code += bytes([0x48, 0x89, 0x04, 0x24])
    code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_TSC_LATEST])
    code += bytes([0x48, 0xC7, 0x44, 0x24, SLOT_EPOCH, 0x02, 0x00, 0x00, 0x00])

    tx("v5")
    hex64(SLOT_TSC_GENESIS)
    tx("v5_tail")

    # 6. Interactive COM1 shell: block for a line, answer it, repeat until HALT.
    if enable_serial_rx:
        tx("shell_ready")
        shell_top = len(code)
        code += bytes([0x48, 0x8D, 0x7C, 0x24, RX_LINE_BUFFER])
        code += bytes([0x31, 0xDB])

        read_byte = len(code)
        poll = len(code)
        code += bytes([0x66, 0xBA, 0xFD, 0x03, 0xEC, 0xA8, COM1_LSR_DR])
        code += bytes([0x74, (poll - (len(code) + 2)) & 0xFF])
        code += bytes([0x66, 0xBA, 0xF8, 0x03, 0xEC])
        code += bytes([0x3C, 0x0D])
        line_done = [jump32(b"\x0F\x84")]
        code += bytes([0x3C, 0x0A])
        line_done.append(jump32(b"\x0F\x84"))
        code += bytes([0x88, 0x07, 0x48, 0xFF, 0xC7, 0xFF, 0xC3])
        code += bytes([0x83, 0xFB, 0x30])
        code += bytes([0x72, (read_byte - (len(code) + 2)) & 0xFF])

        for field in line_done:
            land(field)
        code += bytes([0x85, 0xDB])
        land(jump32(b"\x0F\x84"), shell_top)  # an empty line: read the next one

        code += bytes([0xC6, 0x07, 0x0D, 0xC6, 0x47, 0x01, 0x0A])
        code += bytes([0x83, 0xC3, 0x02])
        tx("rx_prefix")
        code += bytes([0x48, 0x8D, 0x74, 0x24, RX_LINE_BUFFER, 0x89, 0xD9])
        _emit_tx_loop(code, buf_rva=None, length=1, text_rva=text_rva)

        def command(word: bytes) -> int:
            code.extend(bytes([0x8B, 0x44, 0x24, RX_LINE_BUFFER]))
            code.extend(b"\x3D" + word)
            return jump32(b"\x0F\x85")

        def next_line() -> None:
            land(jump32(b"\xE9"), shell_top)

        not_status = command(b"STAT")
        tx("shell_status")
        hex64(SLOT_EPOCH)
        tx("crlf")
        next_line()
        land(not_status)

        not_mem = command(b"MEM\r")
        tx("shell_mem")
        hex64(SLOT_MAP_SIZE)
        tx("shell_mem_descriptor")
        hex64(SLOT_DESCRIPTOR_SIZE)
        tx("shell_mem_tail")
        next_line()
        land(not_mem)

        not_mir = command(b"MIR\r")
        tx("shell_mir")
        next_line()
        land(not_mir)

        not_epoch = command(b"EPOC")
        code += bytes([0x0F, 0x31, 0x48, 0xC1, 0xE2, 0x20, 0x48, 0x09, 0xD0])
        code += bytes([0x48, 0x89, 0x44, 0x24, SLOT_TSC_LATEST])
        code += bytes([0x48, 0xFF, 0x44, 0x24, SLOT_EPOCH])
        tx("shell_epoch")
        hex64(SLOT_EPOCH)
        tx("shell_epoch_tsc")
        hex64(SLOT_TSC_LATEST)
        tx("crlf")
        next_line()
        land(not_epoch)

        not_trap = command(b"TRAP")
        tx("shell_trap")
        code += bytes([0x0F, 0x0B])  # ud2 -> #UD through the Koschei IDT
        land(not_trap)

        not_halt = command(b"HALT")
        tx("shell_halt")
        halt_forever()
        land(not_halt)

        tx("shell_unknown")
        next_line()

    # 7. After ExitBootServices there is no firmware to return to.
    halt_forever()

    # 8. Failure paths.
    for field in no_boot_services:
        land(field)
    code += b"\x48\xB8" + struct.pack("<Q", EFI_INVALID_PARAMETER)
    store_rax(SLOT_STATUS)
    tx("no_boot_services")
    return_with_status = [jump32(b"\xE9")]

    for field in map_failed_before_exit:
        land(field)
    store_rax(SLOT_STATUS)
    tx("map_failed")
    hex64(SLOT_STATUS)
    tx("map_needed")
    hex64(SLOT_MAP_SIZE)
    tx("map_failed_tail")
    return_with_status.append(jump32(b"\xE9"))

    for field in failed_after_exit_attempt:
        land(field)
    store_rax(SLOT_STATUS)
    tx("exit_failed")
    hex64(SLOT_STATUS)
    tx("exit_failed_attempt")
    hex64(SLOT_ATTEMPT)
    tx("exit_failed_tail")
    halt_forever()

    for field in return_with_status:
        land(field)
    code += b"\x48\x8B\x84\x24" + _disp32(SLOT_STATUS)
    epilogue_return_rax()

    # 9. Out-of-line Fail-Closed Morth CPU Exception Handler (.Lmorth_isr_trap)
    isr_rva = text_rva + len(code)
    lea_isr_end_rva = text_rva + lea_isr_pos + 7
    struct.pack_into("<i", code, lea_isr_pos + 3, isr_rva - lea_isr_end_rva)
    tx("trap")
    halt_forever()

    return bytes(code)


def _byte_lines(data: bytes) -> str:
    return "\n".join(
        "    .byte " + ", ".join(f"0x{b:02x}" for b in data[index : index + 16])
        for index in range(0, len(data), 16)
    )


def emit_uefi_x86_64_gas_v1(
    serial_payload: bytes,
    *,
    mir_fingerprint: str,
    halt_mode: str = "return",
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
    text_bytes: bytes = b"",
    rdata_bytes: bytes = b"",
    experimental_page_tables: bool = False,
) -> str:
    """A byte-exact GNU/Clang listing of the ``BOOTX64.EFI`` sections (v5).

    The image is built from the machine code that ``_build_efi_main_machine_code``
    emits, not from assembly source; this listing records exactly those
    ``.text`` and ``.rdata`` bytes so a reviewer can disassemble them. Its
    RIP-relative displacements assume the image's own section layout, so it
    documents the binary and is not meant to be reassembled.
    """

    if halt_mode not in ("return", "halt"):
        raise ValueError(f"unsupported halt_mode: {halt_mode!r}")
    return f"""# Koschei x86-64 UEFI boot prototype v5: byte-exact section listing
# Sealed MIR SHA-256: {mir_fingerprint}
# serial payload bytes: {len(serial_payload)}
# exit_boot_services={exit_boot_services} serial_shell={enable_serial_rx} halt_mode={halt_mode} experimental_page_tables={experimental_page_tables}
# Disassemble with: objdump -D -b binary -m i386:x86-64 -M intel
.intel_syntax noprefix
.section .text
.globl efi_main
efi_main:
{_byte_lines(text_bytes)}

.section .rdata,"dr"
{_byte_lines(rdata_bytes)}
"""


def _rdata_strings(
    serial_payload: bytes,
    conout_utf16le: bytes,
    mir_fingerprint: str,
    *,
    experimental_page_tables: bool,
) -> dict[str, bytes]:
    """Every text the boot code prints, in ``.rdata`` order."""

    return {
        "payload": serial_payload,
        "utf16": conout_utf16le,
        "crlf": CRLF,
        "v2": POST_EBS_BANNER,
        "v2_map": POST_EBS_MAP_FIELD,
        "v2_descriptor": POST_EBS_DESCRIPTOR_FIELD,
        "no_boot_services": NO_BOOT_SERVICES_BANNER,
        "map_failed": MEMORY_MAP_FAILED_BANNER,
        "map_needed": MEMORY_MAP_NEEDED_FIELD,
        "map_failed_tail": MEMORY_MAP_FAILED_TAIL,
        "exit_failed": EXIT_FAILED_BANNER,
        "exit_failed_attempt": EXIT_FAILED_ATTEMPT_FIELD,
        "exit_failed_tail": EXIT_FAILED_TAIL,
        "v3": KERNEL_V3_BANNER,
        "v4": KERNEL_V4_BANNER,
        "v3x": EXPERIMENTAL_PMM_BANNER,
        "v3x_tail": EXPERIMENTAL_PMM_TAIL,
        "v4x": EXPERIMENTAL_CR3_BANNER,
        "v5": KERNEL_V5_BANNER,
        "v5_tail": KERNEL_V5_TAIL,
        "trap": MORTH_TRAP_BANNER,
        "rx_prefix": UART_RX_PREFIX,
        "shell_ready": SHELL_READY_BANNER,
        "shell_status": (
            SHELL_STATUS_EXPERIMENTAL_REPLY if experimental_page_tables else SHELL_STATUS_REPLY
        ),
        "shell_mem": SHELL_MEM_REPLY,
        "shell_mem_descriptor": SHELL_MEM_DESCRIPTOR_FIELD,
        "shell_mem_tail": SHELL_MEM_TAIL,
        "shell_mir": f"[KOSCHEI-SHELL] sealed_mir_sha256={mir_fingerprint}\r\n".encode("utf-8"),
        "shell_epoch": SHELL_EPOCH_REPLY,
        "shell_epoch_tsc": SHELL_EPOCH_TSC_FIELD,
        "shell_halt": SHELL_HALT_REPLY,
        "shell_trap": SHELL_TRAP_REPLY,
        "shell_unknown": SHELL_UNKNOWN_REPLY,
    }


def build_uefi_pe32plus_v1(
    mir: MirGraph,
    *,
    include_banner: bool = True,
    halt_mode: str = "return",
    exit_boot_services: bool = True,
    enable_serial_rx: bool = True,
    experimental_page_tables: bool = False,
) -> UefiBootArtifactV1:
    """Compile a sealed Koschei MirGraph directly into a deterministic ``BOOTX64.EFI`` (v5).

    ``halt_mode`` applies only without ``exit_boot_services``: after
    ExitBootServices the image halts, since no firmware is left to return to.
    The COM1 shell (``enable_serial_rx``) needs ExitBootServices.
    """

    if enable_serial_rx and not exit_boot_services:
        raise UefiBootError("KS4010", "the COM1 shell runs only after ExitBootServices")
    if experimental_page_tables and not exit_boot_services:
        raise UefiBootError("KS4010", "experimental page tables need ExitBootServices")
    serial_payload, crlf_text = evaluate_sealed_mir_serial_output_v1(
        mir,
        include_banner=include_banner,
    )
    conout_utf16le = crlf_text.encode("utf-16le") + b"\x00\x00"
    texts = _rdata_strings(
        serial_payload,
        conout_utf16le,
        mir.fingerprint,
        experimental_page_tables=experimental_page_tables,
    )

    offsets: dict[str, int] = {}
    cursor = 0
    for name, value in texts.items():
        offsets[name] = cursor
        cursor = _align_up(cursor + len(value), 16)
    gdt_offset = cursor
    rdata_buf = bytearray(gdt_offset + len(GDT_TABLE_BYTES))
    for name, value in texts.items():
        rdata_buf[offsets[name] : offsets[name] + len(value)] = value
    rdata_buf[gdt_offset : gdt_offset + len(GDT_TABLE_BYTES)] = GDT_TABLE_BYTES
    rdata_raw = bytes(rdata_buf)

    text_rva = 0x1000

    def machine_code(rdata_rva: int) -> bytes:
        return _build_efi_main_machine_code(
            strings={name: (rdata_rva + offsets[name], len(value)) for name, value in texts.items()},
            gdt_rva=rdata_rva + gdt_offset,
            text_rva=text_rva,
            rdata_rva_val=rdata_rva,
            halt_mode=halt_mode,
            exit_boot_services=exit_boot_services,
            enable_serial_rx=enable_serial_rx,
            experimental_page_tables=experimental_page_tables,
        )

    # Every displacement is a fixed-size rel32, so the code length does not
    # depend on where .rdata lands; one rebuild settles the layout.
    text_raw = machine_code(0x2000)
    rdata_rva = text_rva + _align_up(len(text_raw), SECTION_ALIGNMENT)
    if rdata_rva != 0x2000:
        text_raw = machine_code(rdata_rva)

    text_file_size = _align_up(len(text_raw), FILE_ALIGNMENT)
    rdata_file_size = _align_up(len(rdata_raw), FILE_ALIGNMENT)

    if text_rva + _align_up(len(text_raw), SECTION_ALIGNMENT) != rdata_rva:
        raise AssertionError("UEFI .text length changed with the .rdata placement")

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
        text_bytes=text_raw,
        rdata_bytes=rdata_raw,
        experimental_page_tables=experimental_page_tables,
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
        experimental_page_tables=experimental_page_tables,
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

    # The FAT type is decided by the cluster count alone (Microsoft FAT spec):
    # under 4085 clusters a volume is FAT12 whatever its label says. With one
    # sector per cluster this 4 MiB volume has 8095 clusters, so it is FAT16;
    # 32 FAT sectors hold their 16-bit entries.
    bytes_per_sector = 512
    sectors_per_cluster = 1
    cluster_size = bytes_per_sector * sectors_per_cluster
    total_sectors = 8192
    reserved_sectors = 1
    num_fats = 2
    root_dir_entries = 512
    root_dir_sectors = (root_dir_entries * 32) // bytes_per_sector
    sectors_per_fat = 32

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
    data_clusters = (
        total_sectors - reserved_sectors - num_fats * sectors_per_fat - root_dir_sectors
    ) // sectors_per_cluster
    if not 4085 <= data_clusters < 65525:
        raise AssertionError(f"ESP geometry is not FAT16: {data_clusters} clusters")
    if (data_clusters + 2) * 2 > sectors_per_fat * bytes_per_sector:
        raise AssertionError("FAT16 table does not cover every cluster")
    if 5 + efi_clusters > data_clusters + 2:
        raise UefiBootError("KS4012", "BOOTX64.EFI does not fit the 4 MiB ESP image")

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
        # A fixed, valid FAT date (1980-01-01) keeps the image deterministic.
        for date_offset in (16, 18, 24):
            struct.pack_into("<H", entry, date_offset, (1 << 5) | 1)
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
    # The volume label the boot sector names, as fsck.fat expects it.
    image[root_offset + 64 : root_offset + 96] = _dir_entry(b"KOSCHEI_", b"ESP", 0x08, 0, 0)

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


# OVMF (QEMU q35, 256 MiB) reported a 0x17d0-byte map of 48-byte descriptors.
OVMF_MEASURED_DESCRIPTOR_COUNT = 0x17D0 // 48


def _emulated_memory_map(count: int) -> tuple[UefiMemoryDescriptorV1, ...]:
    """A firmware-like map of ``count`` descriptors: two conventional regions,
    the loaded image and boot-services pages."""

    if count < 3:
        raise ValueError("an emulated memory map needs at least 3 descriptors")
    descriptors = [
        UefiMemoryDescriptorV1(7, 0x0000000000001000, 0x0000000000001000, 159, 0x0F),
        UefiMemoryDescriptorV1(7, 0x0000000000100000, 0x0000000000100000, 32768, 0x0F),
        UefiMemoryDescriptorV1(1, UEFI_IMAGE_BASE, UEFI_IMAGE_BASE, 16, 0x0F),
    ]
    for index in range(count - 3):
        start = 0x0000000010000000 + index * 0x1000
        descriptors.append(UefiMemoryDescriptorV1(4, start, start, 1, 0x0F))
    return tuple(descriptors)


def simulate_uefi_x86_64_serial_v1(
    efi_bytes: bytes,
    *,
    rx_input: bytes = b"",
    trigger_exception_vector: int | None = None,
    memory_descriptor_count: int = OVMF_MEASURED_DESCRIPTOR_COUNT,
    stale_map_key_once: bool = False,
) -> UefiEmulationResult:
    """Deterministic x86-64 PE32+ emulator for testing ``BOOTX64.EFI`` hardware I/O (v5).

    It models what the real-QEMU runs showed: a memory map of
    ``memory_descriptor_count`` descriptors (OVMF's measured size by default),
    optionally a map key that goes stale once, a page-table switch that faults
    when the new tables leave the running code, the stack or the IDT unmapped,
    and a COM1 receiver that stays empty once ``rx_input`` is consumed (the run
    then ends as ``waiting_for_input``). Returning to the firmware after
    ExitBootServices is a contract violation.
    """

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

    descriptors = _emulated_memory_map(memory_descriptor_count)
    map_key_stale_pending = stale_map_key_once

    code_segment_selector = 0
    exit_attempts = 0
    exit_calls = 0
    memory_map_bytes = 0
    descriptor_bytes = 0
    image_text_address = 0
    failure_status = 0
    triple_fault = False
    waiting_for_input = False
    idle_lsr_reads = 0

    steps = 0

    def _snapshot_frame_state() -> None:
        nonlocal titan_remaining_pages, titan_allocated_page_phys, titan_total_usable_pages
        nonlocal tsc_genesis, tsc_latest, active_epoch
        nonlocal exit_attempts, memory_map_bytes, descriptor_bytes, image_text_address, failure_status
        if frame_rsp:
            tsc_genesis = read_u64(frame_rsp + SLOT_TSC_GENESIS)
            titan_remaining_pages = read_u64(frame_rsp + SLOT_PMM_REMAINING)
            tsc_latest = read_u64(frame_rsp + SLOT_TSC_LATEST)
            titan_allocated_page_phys = read_u64(frame_rsp + SLOT_PMM_FIRST_PAGE)
            titan_total_usable_pages = read_u64(frame_rsp + SLOT_CALL_ARG5)
            active_epoch = read_u64(frame_rsp + SLOT_EPOCH)
            exit_attempts = read_u64(frame_rsp + SLOT_ATTEMPT)
            memory_map_bytes = read_u64(frame_rsp + SLOT_MAP_SIZE)
            descriptor_bytes = read_u64(frame_rsp + SLOT_DESCRIPTOR_SIZE)
            image_text_address = read_u64(frame_rsp + SLOT_IMAGE_TEXT)
            failure_status = read_u64(frame_rsp + SLOT_STATUS)

    def _translate(cr3: int, vaddr: int) -> int | None:
        """The 4-level walk the CPU does; ``None`` when a level is not present."""

        entry = cr3
        for shift in (39, 30, 21, 12):
            table = entry & 0x000FFFFFFFFFF000
            entry = read_u64(table + ((vaddr >> shift) & 0x1FF) * 8)
            if not entry & PTE_PRESENT:
                return None
            if shift in (30, 21) and entry & PTE_PS:
                return entry
        return entry

    while rip != return_sentinel_rip and steps < 2_000_000:
        steps += 1
        tsc_counter += 64
        if idle_lsr_reads > 4096:
            # The receiver stayed empty: the shell waits for a line forever.
            _snapshot_frame_state()
            waiting_for_input = True
            regs["rax"] = 0
            break
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
            exit_calls += 1
            if map_key_stale_pending and regs["rdx"] == expected_map_key:
                # The firmware changed the map between GetMemoryMap and the exit.
                map_key_stale_pending = False
                expected_map_key += 1
                regs["rax"] = EFI_INVALID_PARAMETER
            elif regs["rcx"] != image_handle_val or regs["rdx"] != expected_map_key:
                regs["rax"] = EFI_INVALID_PARAMETER
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
            elif b1 == 0x0B:  # ud2 -> #UD (vector 6) through the loaded IDT
                if not idt_loaded or idt_gate_count <= 6:
                    triple_fault = True
                    _snapshot_frame_state()
                    break
                exception_trapped = True
                gate_addr = idt_base + 6 * 16
                rip = read_u16(gate_addr) | (read_u16(gate_addr + 6) << 16) | (read_u32(gate_addr + 8) << 32)
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
                # The CPU now translates through these tables. If they leave the
                # next instruction, the stack or the IDT unmapped, the next fetch
                # or stack access faults and the fault cannot be delivered.
                for needed in (rip + 3, regs["rsp"], idt_base or regs["rsp"]):
                    if _translate(cr3_pml4_phys, needed) is None:
                        triple_fault = True
                if triple_fault:
                    _snapshot_frame_state()
                    break
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
                wx_enforced = text_is_rx and rdata_is_ro_nx and not triple_fault
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
            elif b1 == 0x88 and read_u8(rip + 2) == 0xC1:  # mov r9b, al
                regs["r9"] = (regs["r9"] & ~0xFF) | (regs["rax"] & 0xFF)
                rip += 3
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
            elif b1 == 0xC1 and b2 == 0xC0:  # rol r8, imm8
                count = read_u8(rip + 3) & 63
                value = regs["r8"] & 0xFFFFFFFFFFFFFFFF
                regs["r8"] = ((value << count) | (value >> (64 - count))) & 0xFFFFFFFFFFFFFFFF
                rip += 4
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
            elif b1 == 0x8B and b2 == 0x84 and read_u8(rip + 3) == 0x24:
                regs["r8"] = read_u64(regs["rsp"] + read_s32(rip + 4))
                rip += 8
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
            elif b1 == 0xC7 and b2 == 0x84 and read_u8(rip + 3) == 0x24:
                write_u64(regs["rsp"] + read_s32(rip + 4), read_u32(rip + 8))
                rip += 12
            elif b1 == 0x89 and b2 == 0x84 and read_u8(rip + 3) == 0x24:
                write_u64(regs["rsp"] + read_s32(rip + 4), regs["rax"])
                rip += 8
            elif b1 == 0x8B and b2 == 0x84 and read_u8(rip + 3) == 0x24:
                regs["rax"] = read_u64(regs["rsp"] + read_s32(rip + 4))
                rip += 8
            elif b1 == 0xCB:  # retfq: pop rip, then cs
                rip = read_u64(regs["rsp"])
                code_segment_selector = read_u64(regs["rsp"] + 8) & 0xFFFF
                regs["rsp"] += 16
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
            if b1 in (0xD8, 0xC0, 0xD0, 0xE0, 0xE8):
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
        elif b0 == 0x24:  # and al, imm8
            al_val = (regs["rax"] & 0xFF) & read_u8(rip + 1)
            regs["rax"] = (regs["rax"] & ~0xFF) | al_val
            zf = al_val == 0
            cf = False
            rip += 2
        elif b0 == 0x04:  # add al, imm8
            total = (regs["rax"] & 0xFF) + read_u8(rip + 1)
            regs["rax"] = (regs["rax"] & ~0xFF) | (total & 0xFF)
            zf = (total & 0xFF) == 0
            cf = total > 0xFF
            rip += 2
        elif b0 == 0x44 and read_u8(rip + 1) == 0x88 and read_u8(rip + 2) == 0xC8:  # mov al, r9b
            regs["rax"] = (regs["rax"] & ~0xFF) | (regs["r9"] & 0xFF)
            rip += 3
        elif b0 == 0x6A:  # push imm8 (sign-extended)
            imm8 = read_u8(rip + 1)
            regs["rsp"] -= 8
            write_u64(regs["rsp"], imm8 - 0x100 if imm8 & 0x80 else imm8)
            rip += 2
        elif b0 == 0x50:  # push rax
            regs["rsp"] -= 8
            write_u64(regs["rsp"], regs["rax"])
            rip += 1
        elif b0 == 0xE9:  # jmp rel32
            rip = rip + 5 + read_s32(rip + 1)
        elif b0 == 0xB9:
            regs["rcx"] = read_u32(rip + 1)
            rip += 5
        elif b0 == 0xEE:
            idle_lsr_reads = 0
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
                else:
                    idle_lsr_reads += 1
                regs["rax"] = (regs["rax"] & ~0xFF) | lsr
            elif port == COM1_RBR:
                idle_lsr_reads = 0
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
            and KERNEL_V5_TAIL in bytes(serial_out)
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

    if exit_calls != exit_attempts and boot_services_tombstoned:
        raise UefiBootError(
            "KS4013",
            f"ExitBootServices was called {exit_calls} times but the image reports attempt {exit_attempts}",
        )
    if rip == return_sentinel_rip and boot_services_tombstoned:
        raise UefiBootError(
            "KS4014",
            "violation: efi_main returned to the firmware after ExitBootServices",
        )
    if not waiting_for_input and not triple_fault and rip != return_sentinel_rip and steps >= 2_000_000:
        raise UefiBootError("KS4013", "emulation step budget exhausted")
    _snapshot_frame_state()

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
        code_segment_selector=code_segment_selector,
        exit_boot_services_attempts=exit_attempts,
        memory_map_bytes=memory_map_bytes,
        descriptor_bytes=descriptor_bytes,
        image_text_address=image_text_address,
        failure_status=failure_status,
        triple_fault=triple_fault,
        waiting_for_input=waiting_for_input,
        exit_boot_services_calls=exit_calls,
    )


def expected_serial_v1(
    artifact: UefiBootArtifactV1,
    emulation: UefiEmulationResult,
    *,
    command: str = "",
) -> bytes:
    """The exact COM1 bytes the image must print, given the values its run read.

    The hex fields come from the run (the firmware's map size, the load
    address, the TSC), so this checks that the code prints what it observed
    and nothing it did not. ``command`` is one shell line sent after the
    ready banner.
    """

    out = bytearray(artifact.serial_payload)
    if not artifact.exit_boot_services:
        return bytes(out)
    if emulation.failure_status:
        if emulation.exit_boot_services_calls:
            out += EXIT_FAILED_BANNER + hex_field(emulation.failure_status)
            out += EXIT_FAILED_ATTEMPT_FIELD + hex_field(emulation.exit_boot_services_attempts)
            out += EXIT_FAILED_TAIL
        elif emulation.exit_boot_services_attempts:
            out += MEMORY_MAP_FAILED_BANNER + hex_field(emulation.failure_status)
            out += MEMORY_MAP_NEEDED_FIELD + hex_field(emulation.memory_map_bytes)
            out += MEMORY_MAP_FAILED_TAIL
        else:
            out += NO_BOOT_SERVICES_BANNER
        return bytes(out)
    out += POST_EBS_BANNER + hex_field(emulation.exit_boot_services_attempts)
    out += POST_EBS_MAP_FIELD + hex_field(emulation.memory_map_bytes)
    out += POST_EBS_DESCRIPTOR_FIELD + hex_field(emulation.descriptor_bytes) + CRLF
    out += KERNEL_V3_BANNER + hex_field(emulation.image_text_address) + CRLF
    if artifact.experimental_page_tables:
        out += EXPERIMENTAL_PMM_BANNER + hex_field(emulation.titan_allocated_page_phys)
        out += EXPERIMENTAL_PMM_TAIL
        if emulation.triple_fault:
            return bytes(out)
        out += EXPERIMENTAL_CR3_BANNER
    else:
        out += KERNEL_V4_BANNER
    out += KERNEL_V5_BANNER + hex_field(emulation.tsc_genesis) + KERNEL_V5_TAIL
    if not artifact.enable_serial_rx:
        return bytes(out)
    out += SHELL_READY_BANNER
    line = command.encode("utf-8")[:48]
    if not line:
        return bytes(out)
    out += UART_RX_PREFIX + line + CRLF
    word = (line + b"\r")[:4]
    if word == b"STAT":
        status = SHELL_STATUS_EXPERIMENTAL_REPLY if artifact.experimental_page_tables else SHELL_STATUS_REPLY
        out += status + hex_field(2) + CRLF
    elif word == b"MEM\r":
        out += SHELL_MEM_REPLY + hex_field(emulation.memory_map_bytes)
        out += SHELL_MEM_DESCRIPTOR_FIELD + hex_field(emulation.descriptor_bytes) + SHELL_MEM_TAIL
    elif word == b"MIR\r":
        out += f"[KOSCHEI-SHELL] sealed_mir_sha256={artifact.mir_fingerprint}\r\n".encode("utf-8")
    elif word == b"EPOC":
        out += SHELL_EPOCH_REPLY + hex_field(3) + SHELL_EPOCH_TSC_FIELD + hex_field(emulation.tsc_latest) + CRLF
    elif word == b"TRAP":
        out += SHELL_TRAP_REPLY + MORTH_TRAP_BANNER
    elif word == b"HALT":
        out += SHELL_HALT_REPLY
    else:
        out += SHELL_UNKNOWN_REPLY
    return bytes(out)
