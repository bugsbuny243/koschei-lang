"""Validate actual QEMU UART transcript; never accept fabricated boot text."""
from pathlib import Path
import sys

EXPECTED = (
    b"KOSCHEI-KERNEL BOOT/1 X86_64-UEFI\r\n",
    b"KOSCHEI-KERNEL K0 SERIAL-OWNED\r\n",
    b"KOSCHEI-KERNEL K0 HALT-NO-POLICY\r\n",
)


def verify(serial_path: Path) -> None:
    data = serial_path.read_bytes()
    if b"KOSCHEI-KERNEL REJECT/" in data:
        raise ValueError("UEFI signature rejected")
    if data != b"".join(EXPECTED):
        raise ValueError(f"unexpected UART boot transcript ({data!r})")
    print("KOSCHEI-K0 SERIAL/1 PASS 3 exact records")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python verify_serial.py SERIAL.LOG")
    verify(Path(sys.argv[1]))
