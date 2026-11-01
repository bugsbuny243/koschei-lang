"""Structure and provenance gate: x86-64 UEFI PE, empty import table.

This verifies binary format and non-hosted linkage, NOT runtime correctness
or absence of malicious firmware. QEMU smoke separately checks real boot.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import sys


QEMU_CR3_PF_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-PF-DENIED"
QEMU_CR3_RO_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-RO-WRITE-DENIED"
QEMU_CR3_NX_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-NX-EXEC-DENIED"
QEMU_CR3_MAPPED_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-4K-MAPPED"
QEMU_CR3_WX_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-CODE-WRITE-DENIED"
QEMU_CR3_DATA_NX_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-IMAGE-DATA-NX-DENIED"
QEMU_CR3_LOW_HOLE_MARKER = b"KOSCHEI-KERNEL K0 OWN-CR3-LOW-HOLE-DENIED"


def verify_qemu_only_cr3_probe(
    release: bytes, qemu: bytes, qemu_ro: bytes | None = None,
    qemu_nx: bytes | None = None, qemu_mapped: bytes | None = None,
    qemu_wx: bytes | None = None, qemu_data_nx: bytes | None = None,
    qemu_low_hole: bytes | None = None
) -> None:
    """Require proof marker in test image and prohibit it in shipping EFI."""
    if (QEMU_CR3_PF_MARKER in release or QEMU_CR3_RO_MARKER in release or
            QEMU_CR3_NX_MARKER in release or
            QEMU_CR3_MAPPED_MARKER in release or
            QEMU_CR3_WX_MARKER in release or
            QEMU_CR3_DATA_NX_MARKER in release or
            QEMU_CR3_LOW_HOLE_MARKER in release):
        raise ValueError("unsafe QEMU-only CR3 page fault probe leaked into release")
    if QEMU_CR3_PF_MARKER not in qemu:
        raise ValueError("QEMU image lacks expected CR3 page fault test marker")
    if qemu_ro is not None and QEMU_CR3_RO_MARKER not in qemu_ro:
        raise ValueError("QEMU RO image lacks expected CPU permission-fault marker")
    if qemu_ro is not None and QEMU_CR3_RO_MARKER in qemu:
        raise ValueError("RO-only marker leaked into unmapped-fault image")
    if qemu_nx is not None and QEMU_CR3_NX_MARKER not in qemu_nx:
        raise ValueError("QEMU NX image lacks expected execution-fault marker")
    if qemu_nx is not None and QEMU_CR3_NX_MARKER in qemu:
        raise ValueError("NX-only marker leaked into unmapped-fault image")
    if qemu_mapped is not None and QEMU_CR3_MAPPED_MARKER not in qemu_mapped:
        raise ValueError("QEMU 4K image lacks expected mapped-page marker")
    if qemu_mapped is not None and QEMU_CR3_MAPPED_MARKER in qemu:
        raise ValueError("4K marker leaked into unmapped-only image")
    if qemu_wx is not None and QEMU_CR3_WX_MARKER not in qemu_wx:
        raise ValueError("QEMU W^X image lacks code-write-denial marker")
    if qemu_wx is not None and QEMU_CR3_WX_MARKER in qemu:
        raise ValueError("W^X marker leaked into unmapped-only image")
    if qemu_data_nx is not None and QEMU_CR3_DATA_NX_MARKER not in qemu_data_nx:
        raise ValueError("PE-data-NX image lacks CPU fetch-denial marker")
    if qemu_data_nx is not None and QEMU_CR3_DATA_NX_MARKER in qemu:
        raise ValueError("data-NX marker leaked into unmapped-only image")
    if qemu_low_hole is not None and QEMU_CR3_LOW_HOLE_MARKER not in qemu_low_hole:
        raise ValueError("low-hole EFI lacks real CR3 fault marker")
    if qemu_low_hole is not None and QEMU_CR3_LOW_HOLE_MARKER in qemu:
        raise ValueError("low-hole marker leaked into unmapped-only image")


def verify_uefi_pe(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) < 0x100 or raw[:2] != b"MZ":
        raise ValueError(f"{path}: missing MZ header")
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    if pe > len(raw) - 160 or raw[pe:pe + 4] != b"PE\x00\x00":
        raise ValueError(f"{path}: malformed PE signature")
    coff = pe + 4
    machine = struct.unpack_from("<H", raw, coff)[0]
    sections = struct.unpack_from("<H", raw, coff + 2)[0]
    opt_size = struct.unpack_from("<H", raw, coff + 16)[0]
    opt = coff + 20
    if machine != 0x8664 or not 1 <= sections <= 16:
        raise ValueError(f"{path}: not x86-64 PE")
    if opt_size < 128 or opt + opt_size > len(raw):
        raise ValueError(f"{path}: bad PE32+ optional header")
    magic = struct.unpack_from("<H", raw, opt)[0]
    subsystem = struct.unpack_from("<H", raw, opt + 68)[0]
    number_of_directories = struct.unpack_from("<I", raw, opt + 108)[0]
    imports = struct.unpack_from("<II", raw, opt + 112 + 8)
    if magic != 0x20B or subsystem != 10 or number_of_directories < 2:
        raise ValueError(f"{path}: not an EFI x86-64 PE32+ application")
    if imports != (0, 0):
        raise ValueError(f"{path}: external library/runtime imports forbidden")
    # Source-linked artifact preflight, not a live CR3 permission test.
    # A loaded PE image's physical pages require a separate runtime mapper.
    image_size = struct.unpack_from("<I", raw, opt + 56)[0]
    header_size = struct.unpack_from("<I", raw, opt + 60)[0]
    section_alignment = struct.unpack_from("<I", raw, opt + 32)[0]
    table_offset = opt + opt_size
    if (section_alignment != 4096 or image_size < 4096 or
            image_size > 2 * 1024 * 1024 or image_size % 4096 != 0 or
            header_size < table_offset + sections * 40 or
            header_size > image_size or header_size > len(raw) or
            table_offset > len(raw) or sections > (len(raw) - table_offset) // 40):
        raise ValueError(f"{path}: invalid section table or page granularity")
    occupied = set(range((header_size + 4095) // 4096))
    executable = writable = 0
    for i in range(sections):
        sh = table_offset + i * 40
        virtual_size, virtual_address, raw_size = struct.unpack_from("<III", raw, sh + 8)
        flags = struct.unpack_from("<I", raw, sh + 36)[0]
        byte_length = max(virtual_size, raw_size)
        if (not byte_length or virtual_address % 4096 or
                virtual_address >= image_size or
                byte_length > image_size - virtual_address):
            raise ValueError(f"{path}: malformed PE section #{i}")
        readable = bool(flags & 0x40000000)
        is_exec = bool(flags & 0x20000000)
        is_write = bool(flags & 0x80000000)
        if not readable or (is_exec and is_write):
            raise ValueError(f"{path}: unreadable or W+X PE section #{i}")
        for page in range(virtual_address // 4096,
                          virtual_address // 4096 + (byte_length + 4095) // 4096):
            if page in occupied:
                raise ValueError(f"{path}: overlapping 4KiB section page #{i}")
            occupied.add(page)
            executable += is_exec
            writable += is_write
    if not executable or not writable:
        raise ValueError(f"{path}: missing executable/writable section classes")
    print(f"KOSCHEI-K0 PE-SECTION-WX/1 OK {path.name} "
          f"RX={executable} RW-NX={writable} (file preflight only)")
    digest = hashlib.sha256(raw).hexdigest()
    print(f"KOSCHEI-K0 PE/1 OK {path.name} sha256={digest}")
    return digest


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5, 6, 7, 8, 9):
        raise SystemExit("usage: python verify_pe.py RELEASE.EFI QEMU.EFI [QEMU-RO.EFI] [QEMU-NX.EFI] [QEMU-MAPPED.EFI] [QEMU-WX.EFI] [QEMU-DATA-NX.EFI] [QEMU-LOW-HOLE.EFI]")
    hashes = [verify_uefi_pe(Path(p)) for p in sys.argv[1:]]
    if hashes[0] == hashes[1]:
        raise SystemExit("release and test artifact must differ (QEMU-only port)")
    verify_qemu_only_cr3_probe(
        Path(sys.argv[1]).read_bytes(), Path(sys.argv[2]).read_bytes(),
        Path(sys.argv[3]).read_bytes() if len(sys.argv) >= 4 else None,
        Path(sys.argv[4]).read_bytes() if len(sys.argv) >= 5 else None,
        Path(sys.argv[5]).read_bytes() if len(sys.argv) >= 6 else None,
        Path(sys.argv[6]).read_bytes() if len(sys.argv) >= 7 else None,
        Path(sys.argv[7]).read_bytes() if len(sys.argv) >= 8 else None,
        Path(sys.argv[8]).read_bytes() if len(sys.argv) == 9 else None)
    print("KOSCHEI-K0 TEST-IMAGE-ISOLATION/1 PASS CR3 probe absent from release")
