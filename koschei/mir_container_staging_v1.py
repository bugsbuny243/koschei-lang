"""Staged MIR container ABI for Koschei v4.

Map/Struct literals cannot be lowered as one eager aggregate because source
semantics stop evaluating later entries or fields after an error value. This
small staged ABI lets the lowerer insert explicit CFG checks between each source
expression while keeping construction AST-free.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import SourceLocation
from .type_system import TypeNode


@dataclass(frozen=True, slots=True)
class MirIsRuntimeError:
    """True only for Koschei ``KsError``, not general Result/Option fallibility."""

    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapNew:
    """Create an empty ordinary Map builder with no authority semantics."""

    target: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapInsert:
    """Commit one already-evaluated key/value pair into a staged Map builder."""

    container: int
    key: int
    value: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapFinish:
    """Finalize a staged ordinary Map builder into its runtime Map value."""

    target: int
    container: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructNew:
    """Create an empty builder for a compiler-checked canonical struct identity."""

    target: int
    type_name: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructSet:
    """Commit one already-evaluated field into a staged ordinary Struct builder."""

    container: int
    field: str
    value: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructFinish:
    """Finalize a staged Struct builder after exact field-set validation."""

    target: int
    container: int
    type: TypeNode
    location: SourceLocation
