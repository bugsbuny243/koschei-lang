"""Validate QEMU-only real CPU registers and #PF UART receipts.

Neither serial text nor a CPU snapshot alone proves CR3 ownership: the
corresponding OVMF boot must also exit with the precise debug-exit status.
"""
from pathlib import Path
import re
import sys
from verify_serial import EXPECTED

EXPECTED_PF = (
    b"KOSCHEI-KERNEL K0 CPU-PF-TRAP/1 "
    b"CR2=0000400000000000 ERROR=0000000000000000\r\n"
)
IMAGE_PATTERN = re.compile(
    b"KOSCHEI-KERNEL K0 IMAGE-LIVE/1 "
    b"BASE=([0-9a-f]{16}) SIZE=([0-9a-f]{16})\r\n"
)
VALID_IMAGE_FIXTURE = (
    b"KOSCHEI-KERNEL K0 IMAGE-LIVE/1 "
    b"BASE=0000000000400000 SIZE=0000000000010000\r\n"
)
WALK_PATTERN = re.compile(
    b"KOSCHEI-KERNEL K0 CR3-WALK/1 "
    b"RIPPA=([0-9a-f]{16}) RSPPA=([0-9a-f]{16}) "
    b"CR3=([0-9a-f]{16})\r\n"
)
VALID_WALK_FIXTURE = (
    b"KOSCHEI-KERNEL K0 CR3-WALK/1 "
    b"RIPPA=0000000000400200 RSPPA=0000000000600fef "
    b"CR3=0000000000800000\r\n"
)
FIELD_NAMES = (
    b"CR0", b"CR3", b"CR4", b"EFER", b"RFLAGS", b"CS",
    b"GDTR", b"GDTLIMIT", b"IDTR", b"IDTLIMIT", b"RIP", b"RSP",
)
LIVE_PATTERN = re.compile(
    b"KOSCHEI-KERNEL K0 CPU-LIVE/1" +
    b"".join(b" " + name + b"=([0-9a-f]{16})" for name in FIELD_NAMES) +
    b"\r\n"
)
# Documentation/test fixture only: actual guest values are read and emitted
# at run time, not synthesized from this constant.
VALID_LIVE_FIXTURE = (
    b"KOSCHEI-KERNEL K0 CPU-LIVE/1 "
    b"CR0=0000000080010001 CR3=0000000000800000 "
    b"CR4=0000000000000020 EFER=0000000000000d00 "
    b"RFLAGS=0000000000000002 CS=0000000000000008 "
    b"GDTR=0000000000100000 GDTLIMIT=0000000000000040 "
    b"IDTR=0000000000200000 IDTLIMIT=0000000000000fff "
    b"RIP=0000000000400200 RSP=0000000000600ff0\r\n"
)
EXPECTED_PREFIX = b"".join(EXPECTED[:-1])
EXPECTED_TAIL = EXPECTED_PF + EXPECTED[-1]


def _canonical48(value: int) -> bool:
    return (value >> 48) == (0xffff if value & (1 << 47) else 0)


def validate_live_register_record(record: bytes) -> dict[str, int]:
    match = LIVE_PATTERN.fullmatch(record)
    if not match:
        raise ValueError("malformed/absent actual CPU register record")
    v = {name.decode("ascii"): int(raw, 16)
         for name, raw in zip(FIELD_NAMES, match.groups())}
    cr0_required = (1 << 0) | (1 << 16) | (1 << 31)
    efer_required = (1 << 8) | (1 << 10) | (1 << 11)
    if ((v["CR0"] & cr0_required) != cr0_required or
        not (v["CR4"] & (1 << 5)) or
        v["CR4"] & ((1 << 12) | (1 << 17)) or
        (v["EFER"] & efer_required) != efer_required or
        (v["RFLAGS"] & ((1 << 9) | 2)) != 2 or
        v["CS"] == 0 or v["CS"] & 3 or v["CS"] > 0xffff or
        v["CR3"] == 0 or v["CR3"] & 4095 or
        v["CR3"] & ~0x000ffffffffff000 or
        not all(v[k] and _canonical48(v[k])
                for k in ("GDTR", "IDTR", "RIP", "RSP")) or
        v["GDTLIMIT"] < 23 or v["GDTLIMIT"] > 0xffff or
        v["IDTLIMIT"] < (14 * 16 + 15) or v["IDTLIMIT"] > 0xffff):
        raise ValueError("live CPU register prerequisites not satisfied")
    return v


def verify(serial_path: Path) -> None:
    data = serial_path.read_bytes()
    if b"KOSCHEI-KERNEL REJECT/" in data:
        raise ValueError("guest rejected CPU observation or #PF")
    if len(data) > 8192 or not data.endswith(EXPECTED_TAIL):
        raise ValueError("missing/altered real CPU #PF UART receipt")
    head = data[:-len(EXPECTED_TAIL)]
    index = head.rfind(EXPECTED_PREFIX)
    if index < 0 or b"KOSCHEI-KERNEL" in head[:index]:
        raise ValueError("unexpected, duplicate or missing K0 boot records")
    record = head[index + len(EXPECTED_PREFIX):]
    image = IMAGE_PATTERN.match(record)
    if not image:
        raise ValueError("missing or malformed UEFI LoadedImage boundary receipt")
    image_base, image_size = (int(v, 16) for v in image.groups())
    if (not image_base or image_base & 4095 or
        not 0 < image_size <= 32 * 1024 * 1024 or
        image_base + image_size > 2**64):
        raise ValueError("invalid LoadedImage bounds")
    walk = WALK_PATTERN.match(record, image.end())
    if not walk:
        raise ValueError("missing or malformed real CR3 table-byte walk record")
    rippa, rsppa, root = (int(raw, 16) for raw in walk.groups())
    live = validate_live_register_record(record[walk.end():])
    if (rippa != live["RIP"] or rsppa != live["RSP"] - 1 or
        root != live["CR3"] or
        not (0 < rippa < 256 * 1024 * 1024) or
        not (0 < rsppa < 256 * 1024 * 1024)):
        raise ValueError("active CR3 readback disagrees with live CPU registers")
    if not image_base <= live["RIP"] < image_base + image_size:
        raise ValueError("observed RIP is outside the UEFI loaded image")
    if image_base <= live["RSP"] < image_base + image_size:
        raise ValueError("observed stack unexpectedly overlaps loaded image")
    print("KOSCHEI-K0 CR3-WALK/1 PASS active firmware PTE bytes cross-check RIP/RSP")
    print("KOSCHEI-K0 IMAGE-LIVE/1 PASS UEFI LoadedImage bounds match CPU RIP")
    print("KOSCHEI-K0 CPU-LIVE/1 PASS real register values validated; "
          "firmware-owned CR3 only")
    print("KOSCHEI-K0 CPU-PF/1 PASS exact real-trap CR2/error receipt; "
          "firmware-owned CR3 only")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python verify_cpu_pf_serial.py SERIAL.LOG")
    verify(Path(sys.argv[1]))
