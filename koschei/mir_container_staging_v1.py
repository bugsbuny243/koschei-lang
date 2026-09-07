"""Staged MIR container ABI for Koschei v4.

These instructions are deliberately small. Map/Struct literals cannot be lowered
as one eager aggregate because source semantics stop evaluating later entries or
fields after an error value. A staged ABI lets the lowerer insert explicit CFG
checks between each source expression while keeping construction AST-free.

This module defines representation only. Runtime execution and canonical lowering
must consume these nodes explicitly before the feature is considered implemented.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import SourceLocation
from .type_system import TypeNode


@dataclass(frozen=True, slots=True)
class MirIsRuntimeError:
    """True only for the Koschei runtime error value, not general fallible values.

    Map/Struct source semantics stop on ``KsError`` specifically. Reusing the
    broader Result/Option fallible predicate would incorrectly change semantics.
    """

    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapNew:
    """Create an empty ordinary Map value with no authority semantics."""

    target: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMapInsert:
    """Insert one already-evaluated key/value pair into an ordinary Map.

    Runtime enforcement must preserve String-only keys, duplicate-key rejection,
    and nested capability rejection. The instruction itself never widens or
    manufactures authority.
    """

    container: int
    key: int
    value: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructNew:
    """Create an empty instance of a compiler-checked canonical struct identity."""

    target: int
    type_name: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStructSet:
    """Install one already-evaluated field into a staged ordinary Struct value.

    Runtime enforcement must validate the compiler-known field contract and reject
    nested capabilities. Ordinary Struct values are not capability envelopes.
    """

    container: int
    field: str
    value: int
    type: TypeNode
    location: SourceLocation
