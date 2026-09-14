"""Single authority for stabilized Koschei MIR v4 extension instructions.

These dataclasses are representation-only MIR facts. They carry no authority and
must remain compatible with the canonical MIR validator/fingerprint ABI.
Compatibility modules may re-export these exact class objects, but MUST NOT
redefine them.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import SourceLocation
from .type_system import TypeNode


@dataclass(frozen=True, slots=True)
class MirUnit:
    """Canonical Koschei Unit/Void runtime value; never a host-language sentinel."""

    target: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirFallibleIsSuccess:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirFalliblePayload:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirInterpolate:
    target: int
    items: tuple[int, ...]
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirIsRuntimeError:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirVariantConstruct:
    """Construct one value with an exact compiler-selected ``Owner::Variant`` identity."""

    target: int
    variant: str
    source: int | None
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirVariantIs:
    """Compare one checked value against one compiler-selected variant identity."""

    target: int
    source: int
    variant: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirVariantPayload:
    """Extract payload only on a CFG path proven for the exact same variant."""

    target: int
    source: int
    variant: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapNew:
    target: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapInsert:
    """`object` is builder SSA; `arguments` is exactly `(key, value)` SSA."""

    object: int
    arguments: tuple[int, int]
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapFinish:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructNew:
    target: int
    type_name: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructSet:
    """`object` is builder SSA and `source` is the field value SSA."""

    object: int
    field: str
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructFinish:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


MIR_V4_EXTENSION_INSTRUCTION_TYPES = (
    MirUnit,
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirInterpolate,
    MirIsRuntimeError,
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
    MirMapNew,
    MirMapInsert,
    MirMapFinish,
    MirStructNew,
    MirStructSet,
    MirStructFinish,
)
