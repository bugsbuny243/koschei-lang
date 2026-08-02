"""Shared v0.10 syntax nodes and token kinds."""
from __future__ import annotations
from dataclasses import dataclass
from . import ast_nodes as ast

@dataclass(frozen=True, slots=True)
class TokenKind:
    name: str

@dataclass(frozen=True, slots=True)
class LetStatement:
    name: str
    is_mutable: bool
    value: ast.Expression
    location: ast.SourceLocation
    annotation: ast.TypeRef | None = None

@dataclass(frozen=True, slots=True)
class BreakStatement:
    location: ast.SourceLocation

@dataclass(frozen=True, slots=True)
class ContinueStatement:
    location: ast.SourceLocation

@dataclass(frozen=True, slots=True)
class MatchArm:
    variant: str
    binding: str | None
    body: ast.Expression | ast.Block
    location: ast.SourceLocation

class BreakSignal(Exception):
    pass

class ContinueSignal(Exception):
    pass

def install_node_references() -> None:
    from . import _parser_v09, parser, semantic, interpreter, codegen_go, typed_hir, mir_ir
    ast.LetStatement = LetStatement
    ast.BreakStatement = BreakStatement
    ast.ContinueStatement = ContinueStatement
    ast.MatchArm = MatchArm
    for module in (_parser_v09, parser, semantic, interpreter, codegen_go, typed_hir, mir_ir):
        module.LetStatement = LetStatement
        module.BreakStatement = BreakStatement
        module.ContinueStatement = ContinueStatement
        module.MatchArm = MatchArm
