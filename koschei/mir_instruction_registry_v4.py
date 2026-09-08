"""Canonical MIR v4 instruction registry.

This module is the single versioned registry for every instruction class that
may appear in a sealed or executable MIR v4 graph. Core classes remain
implemented in ``mir_ir`` during bootstrap migration; extension classes are
implemented in ``mir_extension_instructions_v4``. Consumers MUST use this
registry when they need the complete v4 instruction universe rather than
inventing a second list or accepting arbitrary dataclass-shaped instructions.
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
from .mir_ir import (
    MirAstFallback,
    MirBinary,
    MirBind,
    MirCall,
    MirConst,
    MirInstruction as MirCoreInstruction,
    MirIterHasNext,
    MirIterInit,
    MirIterNext,
    MirList,
    MirLoad,
    MirMember,
    MirStore,
    MirUnary,
)


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


MIR_V4_CORE_INSTRUCTION_TYPES = (
    MirConst,
    MirLoad,
    MirBind,
    MirStore,
    MirUnary,
    MirBinary,
    MirList,
    MirIterInit,
    MirIterHasNext,
    MirIterNext,
    MirMember,
    MirCall,
    MirAstFallback,
)

MIR_V4_INSTRUCTION_TYPES = (
    *MIR_V4_CORE_INSTRUCTION_TYPES,
    *MIR_V4_EXTENSION_INSTRUCTION_TYPES,
)


def is_mir_v4_instruction(value: object) -> bool:
    """Return whether ``value`` is one exact registered MIR v4 instruction."""

    return type(value) in MIR_V4_INSTRUCTION_TYPES


def require_mir_v4_instruction(value: object) -> None:
    """Fail closed when an instruction class is outside the v4 registry.

    Exact-type membership is intentional. Subclassing a registered dataclass
    must not create an implicit new MIR opcode or inherit execution authority.
    """

    if not is_mir_v4_instruction(value):
        raise ValueError(
            "unregistered MIR v4 instruction class: "
            f"{type(value).__module__}.{type(value).__qualname__}"
        )


def require_mir_v4_graph_registry(mir_graph: object) -> None:
    """Require every instruction in a graph to belong to the exact v4 registry.

    This is representation validation only; it does not replace MIR sealing,
    SSA/control-flow validation, capability checks, or execution policy.
    """

    modules = getattr(mir_graph, "modules", None)
    if modules is None or not hasattr(modules, "values"):
        raise ValueError("MIR v4 registry validation requires a module graph")
    for module in modules.values():
        for function in getattr(module, "functions", ()):
            for block in getattr(function, "blocks", ()):
                for instruction in getattr(block, "instructions", ()):
                    require_mir_v4_instruction(instruction)


def is_mir_v4_extension_instruction(value: object) -> bool:
    return type(value) in MIR_V4_EXTENSION_INSTRUCTION_TYPES
