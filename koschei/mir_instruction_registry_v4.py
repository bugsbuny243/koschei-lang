"""Canonical MIR v4 instruction registry.

This module is the single versioned registry for every instruction class that
may appear in a sealed MIR v4 graph. Core classes remain implemented in
``mir_ir`` during bootstrap migration; extension classes are implemented in
``mir_extension_instructions_v4``. Consumers should use this registry when they
need the complete v4 instruction universe rather than inventing a second list.
"""
from __future__ import annotations

from typing import TypeAlias

from .mir_extension_instructions_v4 import (
    MIR_V4_EXTENSION_INSTRUCTION_TYPES,
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirInterpolate,
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)
from .mir_ir import MirInstruction as MirCoreInstruction


MirInstructionV4: TypeAlias = (
    MirCoreInstruction
    | MirFallibleIsSuccess
    | MirFalliblePayload
    | MirInterpolate
    | MirIsRuntimeError
    | MirMapNew
    | MirMapInsert
    | MirMapFinish
    | MirStructNew
    | MirStructSet
    | MirStructFinish
)


def is_mir_v4_extension_instruction(value: object) -> bool:
    return isinstance(value, MIR_V4_EXTENSION_INSTRUCTION_TYPES)
