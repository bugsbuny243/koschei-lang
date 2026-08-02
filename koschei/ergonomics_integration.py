"""Compatibility integration for the isolated v0.10 ergonomics surface.

The v5 bootstrap still has legacy generic and MIR compatibility views.  This
module teaches those views only about the new syntax without changing their
existing contracts for programs that do not use v0.10 features.
"""
from __future__ import annotations

from dataclasses import replace

from . import ast_nodes as ast
from . import codegen_go
from . import ergonomics_semantics as semantics_v010
from . import legacy_generics
from . import mir_ir
from . import semantic
from . import typed_hir

_INSTALLED = False


def _semantic_statement(self, statement):
    # Preserve every pre-v0.10 let rule, especially Data fallibility.  The new
    # path is needed only when the user actually wrote an annotation.
    if isinstance(statement, ast.LetStatement) and statement.annotation is None:
        return semantics_v010._statement.original(self, statement)
    return _semantic_statement.v010(self, statement)


def _typed_statement(self, statement):
    if isinstance(statement, ast.LetStatement) and statement.annotation is None:
        return semantics_v010._typed_statement.original(self, statement)
    return _typed_statement.v010(self, statement)


def _legacy_statement(self, statement):
    if isinstance(statement, (ast.BreakStatement, ast.ContinueStatement)):
        return statement
    return _legacy_statement.original(self, statement)


def _legacy_expression(self, expression):
    if isinstance(expression, ast.MatchExpression) and any(
        isinstance(arm.body, ast.Block) for arm in expression.arms
    ):
        return replace(
            expression,
            value=self.expression(expression.value),
            arms=tuple(
                ast.MatchArm(
                    arm.variant,
                    arm.binding,
                    self.block(arm.body)
                    if isinstance(arm.body, ast.Block)
                    else self.expression(arm.body),
                    arm.location,
                )
                for arm in expression.arms
            ),
        )
    return _legacy_expression.original(self, expression)


def _contains_loop_control(block: ast.Block) -> bool:
    for statement in block.statements:
        if isinstance(statement, (ast.BreakStatement, ast.ContinueStatement)):
            return True
        if isinstance(statement, ast.IfStatement):
            if _contains_loop_control(statement.then_block):
                return True
            branch = statement.else_branch
            if isinstance(branch, ast.Block) and _contains_loop_control(branch):
                return True
            if isinstance(branch, ast.IfStatement) and _contains_loop_control(
                ast.Block((branch,))
            ):
                return True
        elif isinstance(statement, (ast.WhileStatement, ast.ForStatement)):
            # A nested loop owns its own control statements; do not make the
            # outer loop's legacy representation depend on them.
            continue
        elif isinstance(statement, ast.ExpressionStatement):
            expression = statement.expression
            if isinstance(expression, ast.MatchExpression):
                for arm in expression.arms:
                    if isinstance(arm.body, ast.Block) and _contains_loop_control(
                        arm.body
                    ):
                        return True
    return False


def _mir_statement(self, statement):
    if isinstance(statement, ast.ForStatement) and not _contains_loop_control(
        statement.body
    ):
        # Keep the established V5 fallback contract for ordinary for loops.
        return semantics_v010._mir_statement.original(self, statement)
    return _mir_statement.v010(self, statement)


def _normalize_native_helper_source() -> None:
    marker = "\nfunc ksMod("
    if marker not in codegen_go.RUNTIME_PRELUDE:
        return
    head, tail = codegen_go.RUNTIME_PRELUDE.split(marker, 1)
    # The helper is appended from a Python raw string. Convert only that tail's
    # indentation escapes; existing runtime strings remain untouched.
    tail = (marker + tail).replace("\\t", "\t")
    codegen_go.RUNTIME_PRELUDE = head + tail


def install_integration_v010() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _semantic_statement.v010 = semantic.SemanticChecker._check_statement
    semantic.SemanticChecker._check_statement = _semantic_statement

    _typed_statement.v010 = typed_hir.TypedHIRChecker.check_statement
    typed_hir.TypedHIRChecker.check_statement = _typed_statement

    _legacy_statement.original = legacy_generics._Rewriter.statement
    legacy_generics._Rewriter.statement = _legacy_statement
    _legacy_expression.original = legacy_generics._Rewriter.expression
    legacy_generics._Rewriter.expression = _legacy_expression

    _mir_statement.v010 = mir_ir._FunctionLowerer._lower_statement
    mir_ir._FunctionLowerer._lower_statement = _mir_statement

    _normalize_native_helper_source()
    _INSTALLED = True
