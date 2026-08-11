"""V5 AST extensions that leave the frozen v0.9 node ABI intact."""

from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import EnumDeclaration, FunctionDeclaration, StructDeclaration


@dataclass(frozen=True, slots=True)
class GenericFunctionDeclaration(FunctionDeclaration):
    """A function declaration with inferred source-level type parameters."""

    type_parameters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GenericStructDeclaration(StructDeclaration):
    """A generic struct, optionally carrying a compiler-enforced typestate axis."""

    type_parameters: tuple[str, ...] = ()
    is_stateful: bool = False


@dataclass(frozen=True, slots=True)
class GenericEnumDeclaration(EnumDeclaration):
    """An enum declaration whose payload contracts may reference type parameters."""

    type_parameters: tuple[str, ...] = ()
