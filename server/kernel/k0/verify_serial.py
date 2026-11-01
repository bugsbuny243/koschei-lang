"""Validate actual QEMU UART transcript; never accept fabricated boot text."""
from pathlib import Path
import sys

EXPECTED = (
    b"KOSCHEI-KERNEL BOOT/1 X86_64-UEFI\r\n",
    b"KOSCHEI-KERNEL K0 SERIAL-OWNED\r\n",
    b"KOSCHEI-KERNEL K0 LOADED-IMAGE-VALIDATED\r\n",
    b"KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED\r\n",
    b"KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED\r\n",
    b"KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED\r\n",
    b"KOSCHEI-KERNEL K0 PAGE-POOL-PROBED\r\n",
    b"KOSCHEI-KERNEL K0 PAGE-TABLE-FRAMES-ROUNDTRIP\r\n",
    b"KOSCHEI-KERNEL K0 OWN-CR3-PE-4K-WX\r\n",
    b"KOSCHEI-KERNEL K0 OWN-CR3-PF-DENIED\r\n",
    b"KOSCHEI-KERNEL K0 HALT-NO-POLICY\r\n",
)


EXPECTED_READONLY = EXPECTED[:-2] + (
    b"KOSCHEI-KERNEL K0 OWN-CR3-RO-WRITE-DENIED\r\n",
    EXPECTED[-1],
)
EXPECTED_NX = EXPECTED[:-2] + (
    b"KOSCHEI-KERNEL K0 OWN-CR3-NX-EXEC-DENIED\r\n",
    EXPECTED[-1],
)
EXPECTED_MAPPED = EXPECTED[:-2] + (
    b"KOSCHEI-KERNEL K0 OWN-CR3-4K-MAPPED\r\n",
) + EXPECTED[-2:]
EXPECTED_CODEWX = EXPECTED[:-2] + (
    b"KOSCHEI-KERNEL K0 OWN-CR3-CODE-WRITE-DENIED\r\n",
    EXPECTED[-1],
)


def verify(serial_path: Path, mode: str = "missing") -> None:
    data = serial_path.read_bytes()
    if b"KOSCHEI-KERNEL REJECT/" in data:
        raise ValueError("UEFI signature rejected")
    # OVMF emits its own ANSI screen-clearing and BdsDxe boot messages on
    # the same emulated UART *before* our code starts. Keep these separate
    # from the exact Koschei suffix. No extra Koschei record,
    # duplicate successful boot marker, trailing bytes or oversized preface.
    if mode not in ("missing", "ro", "nx", "mapped", "codewx"):
        raise ValueError("unknown QEMU test mode")
    expected_lines = (EXPECTED_READONLY if mode == "ro" else
                      EXPECTED_NX if mode == "nx" else
                      EXPECTED_MAPPED if mode == "mapped" else
                      EXPECTED_CODEWX if mode == "codewx" else EXPECTED)
    expected = b"".join(expected_lines)
    if not data.endswith(expected) or len(data) > 8192:
        raise ValueError(f"missing or altered Koschei UART transcript ({data[-512:]!r})")
    firmware_prefix = data[:-len(expected)]
    if b"KOSCHEI-KERNEL" in firmware_prefix:
        raise ValueError("unexpected pre-boot Koschei claim in firmware prefix")
    print(f"KOSCHEI-K0 SERIAL/1 PASS exact {len(expected_lines)} Koschei records after firmware preface mode={mode}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python verify_serial.py SERIAL.LOG [missing|ro|nx|mapped|codewx]")
    verify(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else "missing")
