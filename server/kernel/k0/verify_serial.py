"""Validate actual QEMU UART transcript; never accept fabricated boot text."""
from pathlib import Path
import sys

EXPECTED = (
    b"KOSCHEI-KERNEL BOOT/1 X86_64-UEFI\r\n",
    b"KOSCHEI-KERNEL K0 SERIAL-OWNED\r\n",
    b"KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED\r\n",
    b"KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED\r\n",
    b"KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED\r\n",
    b"KOSCHEI-KERNEL K0 PAGE-POOL-PROBED\r\n",
    b"KOSCHEI-KERNEL K0 PAGE-TABLE-FRAMES-ROUNDTRIP\r\n",
    b"KOSCHEI-KERNEL K0 HALT-NO-POLICY\r\n",
)


def verify(serial_path: Path) -> None:
    data = serial_path.read_bytes()
    if b"KOSCHEI-KERNEL REJECT/" in data:
        raise ValueError("UEFI signature rejected")
    # OVMF emits its own ANSI screen-clearing and BdsDxe boot messages on
    # the same emulated UART *before* our code starts. Keep these separate
    # from the exact Koschei suffix. No extra Koschei record,
    # duplicate successful boot marker, trailing bytes or oversized preface.
    expected = b"".join(EXPECTED)
    if not data.endswith(expected) or len(data) > 8192:
        raise ValueError(f"missing or altered Koschei UART transcript ({data[-512:]!r})")
    firmware_prefix = data[:-len(expected)]
    if b"KOSCHEI-KERNEL" in firmware_prefix:
        raise ValueError("unexpected pre-boot Koschei claim in firmware prefix")
    print("KOSCHEI-K0 SERIAL/1 PASS exact eight Koschei records after firmware preface")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python verify_serial.py SERIAL.LOG")
    verify(Path(sys.argv[1]))
