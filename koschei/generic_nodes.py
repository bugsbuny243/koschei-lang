"""V5 AST extensions that leave the frozen v0.9 node ABI intact."""

from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import FunctionDeclaration


@dataclass(frozen=True, slots=True)
class GenericFunctionDeclaration(FunctionDeclaration):
    """A function declaration with inferred source-level type parameters."""

    type_parameters: tuple[str, ...] = ()
