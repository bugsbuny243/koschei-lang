"""Validate real QEMU-only CPU #PF UART receipt on firmware-owned CR3.

A printed record alone is insufficient: qemu_smoke.sh also requires debug-exit
status 33 from a genuine OVMF boot and hashes the resulting UART transcript.
"""
from pathlib import Path
import sys
from verify_serial import EXPECTED

EXPECTED_PF = (
    b"KOSCHEI-KERNEL K0 CPU-PF-TRAP/1 "
    b"CR2=0000400000000000 ERROR=0000000000000000\r\n"
)
EXPECTED_RECORDS = EXPECTED[:-1] + (EXPECTED_PF,) + EXPECTED[-1:]


def verify(path: Path) -> None:
    raw = path.read_bytes()
    expected = b"".join(EXPECTED_RECORDS)
    if b"KOSCHEI-KERNEL REJECT/" in raw:
        raise ValueError("kernel rejected the CPU #PF probe")
    if len(raw) > 8192 or not raw.endswith(expected):
        raise ValueError(f"invalid CPU #PF UART transcript ({raw[-512:]!r})")
    firmware_prefix = raw[:-len(expected)]
    if b"KOSCHEI-KERNEL" in firmware_prefix:
        raise ValueError("unexpected extra/duplicate CPU #PF receipt")
    print("KOSCHEI-K0 CPU-PF/1 PASS exact real-trap CR2/error receipt; "
          "firmware-owned CR3 only")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python verify_cpu_pf_serial.py SERIAL.LOG")
    verify(Path(sys.argv[1]))
