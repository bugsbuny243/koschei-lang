"""Staged MIR container ABI for Koschei v4.

Map/Struct literals cannot be lowered as one eager aggregate because source
semantics stop evaluating later entries or fields after an error value. Field
names intentionally reuse the canonical MIR validator's existing SSA-use ABI
(`source`, `object`, `arguments`) instead of creating a second validator path.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import SourceLocation
from .type_system import TypeNode


@dataclass(frozen=True, slots=True)
class MirIsRuntimeError:
    target: int
    source: int
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
