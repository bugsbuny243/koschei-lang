"""Koschei Surface Program (KSP1) deterministic bytecode core.

This is a closed, authority-free UI/render instruction format for Koschei
Surface. It is intentionally not JavaScript-like and exposes no ambient host
objects or dynamic code generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib

_CTX = b"koschei.surface-program/v1\x00"
_MAGIC = b"KSP1"


class SurfaceBytecodeError(ValueError):
    pass


class SurfaceOp(IntEnum):
    FRAME_BEGIN = 0x01
    FRAME_END = 0x02
    CLEAR = 0x10
    SAVE = 0x11
    RESTORE = 0x12
    TRANSLATE = 0x13
    SCALE = 0x14
    ROTATE_MILLI = 0x15
    STROKE = 0x20
    FILL = 0x21
    LINE = 0x22
    CIRCLE = 0x23
    ARC = 0x24
    TEXT = 0x25
    DASH = 0x26
    GLOW = 0x27
    INPUT_BIND = 0x30
    CELL_SET = 0x31
    CELL_ADD = 0x32
    OBSERVER_READ = 0x40


@dataclass(frozen=True, slots=True)
class SurfaceInstructionV1:
    op: SurfaceOp
    args: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceProgramV1:
    instructions: tuple[SurfaceInstructionV1, ...]
    bytecode: bytes
    program_digest: bytes
    authority: bool = False


def _i64(value: int) -> bytes:
    if not isinstance(value, int) or not (-(1 << 63) <= value < (1 << 63)):
        raise SurfaceBytecodeError("surface argument must fit signed i64")
    return value.to_bytes(8, "big", signed=True)


def encode_surface_program_v1(instructions: tuple[SurfaceInstructionV1, ...]) -> SurfaceProgramV1:
    if not isinstance(instructions, tuple):
        raise SurfaceBytecodeError("instructions must be an immutable tuple")
    if len(instructions) > 65535:
        raise SurfaceBytecodeError("surface program instruction budget exceeded")
    out = bytearray(_MAGIC)
    out.extend(len(instructions).to_bytes(2, "big"))
    for ins in instructions:
        if not isinstance(ins, SurfaceInstructionV1) or not isinstance(ins.op, SurfaceOp):
            raise SurfaceBytecodeError("unknown or invalid Surface instruction")
        if len(ins.args) > 16:
            raise SurfaceBytecodeError("surface instruction argument budget exceeded")
        out.append(int(ins.op))
        out.append(len(ins.args))
        for arg in ins.args:
            out.extend(_i64(arg))
    blob = bytes(out)
    digest = hashlib.sha3_256(_CTX + blob).digest()
    return SurfaceProgramV1(instructions, blob, digest, False)


def decode_surface_program_v1(blob: bytes) -> SurfaceProgramV1:
    if not isinstance(blob, bytes) or len(blob) < 6 or blob[:4] != _MAGIC:
        raise SurfaceBytecodeError("invalid KSP1 bytecode header")
    count = int.from_bytes(blob[4:6], "big")
    pos = 6
    instructions: list[SurfaceInstructionV1] = []
    for _ in range(count):
        if pos + 2 > len(blob):
            raise SurfaceBytecodeError("truncated KSP1 instruction")
        raw_op = blob[pos]; argc = blob[pos + 1]; pos += 2
        try:
            op = SurfaceOp(raw_op)
        except ValueError as exc:
            raise SurfaceBytecodeError("unknown KSP1 opcode") from exc
        if argc > 16 or pos + argc * 8 > len(blob):
            raise SurfaceBytecodeError("invalid KSP1 argument frame")
        args = []
        for _ in range(argc):
            args.append(int.from_bytes(blob[pos:pos + 8], "big", signed=True)); pos += 8
        instructions.append(SurfaceInstructionV1(op, tuple(args)))
    if pos != len(blob):
        raise SurfaceBytecodeError("trailing bytes after KSP1 program")
    return encode_surface_program_v1(tuple(instructions))
