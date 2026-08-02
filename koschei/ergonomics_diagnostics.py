"""Dynamic, localized diagnostic details for v0.10 ergonomics errors."""
from __future__ import annotations

from . import ast_nodes as ast
from . import cli
from . import diagnostics
from . import semantic

_INSTALLED = False


def _with_details(error, *, en: str, tr: str):
    error.v010_details = {"en": en, "tr": tr}
    return error


def _expression(self, expression):
    try:
        return _expression.original(self, expression)
    except semantic.SemanticError as error:
        if (
            error.code == "KS3201"
            and isinstance(expression, ast.AssignmentExpression)
            and isinstance(expression.target, ast.MemberExpression)
            and isinstance(expression.target.object, ast.Identifier)
        ):
            name = expression.target.object.name
            raise _with_details(
                error,
                en=(
                    f"'{name}' is immutable; declare the struct with "
                    f"'let mut {name} = ...' before assigning a field."
                ),
                tr=(
                    f"'{name}' değişmez; alan atamak için struct değerini "
                    f"'let mut {name} = ...' ile tanımlayın."
                ),
            ) from error
        raise


def _diagnostic_payload(message, *, locale="en", source=None, error=None):
    payload = _diagnostic_payload.original(
        message,
        locale=locale,
        source=source,
        error=error,
    )
    details = getattr(error, "v010_details", None)
    if details:
        payload["message"] = details[diagnostics.normalize_locale(locale)]
    return payload


def install_diagnostics_v010() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _expression.original = semantic.SemanticChecker._check_expression
    semantic.SemanticChecker._check_expression = _expression

    _diagnostic_payload.original = diagnostics.diagnostic_payload
    diagnostics.diagnostic_payload = _diagnostic_payload
    # The CLI imported this function before the v0.10 installer ran. Keep JSON
    # diagnostics on the same dynamic-detail contract as human rendering.
    cli.diagnostic_payload = _diagnostic_payload
    _INSTALLED = True
