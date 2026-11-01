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


def verify_qemu_only_cr3_probe(release: bytes, qemu: bytes) -> None:
    """Require proof marker in test image and prohibit it in shipping EFI."""
    if QEMU_CR3_PF_MARKER in release:
        raise ValueError("unsafe QEMU-only CR3 page fault probe leaked into release")
    if QEMU_CR3_PF_MARKER not in qemu:
        raise ValueError("QEMU image lacks expected CR3 page fault test marker")


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
    digest = hashlib.sha256(raw).hexdigest()
    print(f"KOSCHEI-K0 PE/1 OK {path.name} sha256={digest}")
    return digest


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python verify_pe.py RELEASE.EFI QEMU.EFI")
    hashes = [verify_uefi_pe(Path(p)) for p in sys.argv[1:]]
    if hashes[0] == hashes[1]:
        raise SystemExit("release and test artifact must differ (QEMU-only port)")
    verify_qemu_only_cr3_probe(Path(sys.argv[1]).read_bytes(),
                              Path(sys.argv[2]).read_bytes())
    print("KOSCHEI-K0 TEST-IMAGE-ISOLATION/1 PASS CR3 probe absent from release")
