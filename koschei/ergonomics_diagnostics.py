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


def _annotation_error(statement, actual):
    expected = str(statement.annotation)
    error = semantic.SemanticError(
        "KS1301",
        f"Beklenen {expected}, bulunan {actual or 'bilinmiyor'}.",
        statement.location,
    )
    return _with_details(
        error,
        en=f"Expected {expected}, found {actual or 'unknown'}.",
        tr=f"Beklenen {expected}, bulunan {actual or 'bilinmiyor'}.",
    )


def _statement(self, statement):
    if isinstance(statement, ast.LetStatement) and statement.annotation is not None:
        actual = self._check_expression(statement.value)
        expected = str(statement.annotation)
        base = expected.split("<", 1)[0]

        # The legacy semantic checker represents collections coarsely as List or
        # Map. Typed HIR runs immediately afterwards and retains the complete
        # List<T>/Map<String,V> contract. Storing the generic spelling here would
        # make legacy `.get()` look like an unscoped capability call.
        if base in {"List", "Map"}:
            if actual not in {base, None, "_"}:
                raise _annotation_error(statement, actual)
            self._declare(
                semantic.Symbol(
                    statement.name,
                    base,
                    statement.is_mutable,
                    statement.location,
                )
            )
            self.variable_count += 1
            return

        try:
            return _statement.original(self, statement)
        except semantic.SemanticError as error:
            if error.code == "KS1301":
                raise _with_details(
                    error,
                    en=f"Expected {expected}, found {actual or 'unknown'}.",
                    tr=f"Beklenen {expected}, bulunan {actual or 'bilinmiyor'}.",
                ) from error
            raise
    return _statement.original(self, statement)


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
        message, locale=locale, source=source, error=error
    )
    details = getattr(error, "v010_details", None)
    if details:
        payload["message"] = details[diagnostics.normalize_locale(locale)]
    return payload


def install_diagnostics_v010() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _statement.original = semantic.SemanticChecker._check_statement
    semantic.SemanticChecker._check_statement = _statement
    _expression.original = semantic.SemanticChecker._check_expression
    semantic.SemanticChecker._check_expression = _expression

    _diagnostic_payload.original = diagnostics.diagnostic_payload
    diagnostics.diagnostic_payload = _diagnostic_payload
    # The CLI imported this function before the v0.10 installer ran. Keep JSON
    # diagnostics on the same dynamic-detail contract as human rendering.
    cli.diagnostic_payload = _diagnostic_payload
    _INSTALLED = True
