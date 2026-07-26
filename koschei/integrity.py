"""Backend-independent compiler integrity checks.

This pass runs before the ordinary semantic/type checker. It prevents source
program mistakes from leaking into the interpreter or native backend and keeps
control-flow rules in one small, testable layer.
"""

from __future__ import annotations

from .ast_nodes import (
    Block,
    ForStatement,
    IfStatement,
    Program,
    ReturnStatement,
    Statement,
    WhileStatement,
)
from .semantic import SemanticError


def _error(code: str, message: str, statement) -> None:
    raise SemanticError(code, message, statement.location)


def _validate_top_level(program: Program) -> None:
    for kind, declarations in (
        ("function", program.declarations),
        ("struct", program.structs),
        ("enum", program.enums),
    ):
        seen: set[str] = set()
        for declaration in declarations:
            if declaration.name in seen:
                _error(
                    "KS1102",
                    f"'{declaration.name}' {kind} is declared more than once in the global scope.",
                    declaration,
                )
            seen.add(declaration.name)

    struct_names = {declaration.name for declaration in program.structs}
    for declaration in program.enums:
        if declaration.name in struct_names:
            _error(
                "KS1701",
                f"'{declaration.name}' cannot be declared as both a struct and an enum.",
                declaration,
            )


def _check_block(block: Block, function) -> bool:
    terminated = False
    for statement in block.statements:
        if terminated:
            _error(
                "KS1305",
                "This statement is unreachable because the previous control flow always returns.",
                statement,
            )
        terminated = _check_statement(statement, function)
    return terminated


def _check_statement(statement: Statement, function) -> bool:
    if isinstance(statement, ReturnStatement):
        if function.return_type is None and statement.value is not None and function.name != "main":
            _error(
                "KS1304",
                f"'{function.name}' is a Void function and cannot return a value.",
                statement,
            )
        return True

    if isinstance(statement, IfStatement):
        then_returns = _check_block(statement.then_block, function)
        else_returns = False
        if isinstance(statement.else_branch, Block):
            else_returns = _check_block(statement.else_branch, function)
        elif isinstance(statement.else_branch, IfStatement):
            else_returns = _check_statement(statement.else_branch, function)
        return statement.else_branch is not None and then_returns and else_returns

    if isinstance(statement, WhileStatement):
        _check_block(statement.body, function)
        return False

    if isinstance(statement, ForStatement):
        _check_block(statement.body, function)
        return False

    return False


def check_program_integrity(program: Program) -> None:
    """Validate declaration uniqueness and function return control flow."""

    _validate_top_level(program)
    for function in program.declarations:
        always_returns = _check_block(function.body, function)
        if function.return_type is not None and not always_returns:
            _error(
                "KS1303",
                f"'{function.name}' declares return type {function.return_type} but not every control-flow path returns a value.",
                function,
            )
