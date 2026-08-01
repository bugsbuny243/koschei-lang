"""Public diagnostic and fallibility boundary for the opaque Data ABI."""

from __future__ import annotations

from . import interpreter as _runtime
from . import semantic as _semantic
from .ast_nodes import CallExpression, Identifier, LetStatement

_INSTALLED = False
_ORIGINAL_CHECK_EXPRESSION = None
_ORIGINAL_CHECK_STATEMENT = None
_ORIGINAL_INVOKE = None


def _is_data_call(expression) -> bool:
    return (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in {"parse_json", "encode_json"}
    )


def _public_code(text: str) -> str:
    if text.startswith("KS36"):
        return "KS37" + text[4:]
    return text


def _check_expression(self, expression):
    if _is_data_call(expression):
        name = expression.callee.name
        if len(expression.arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301",
                f"{name}() 1 argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        actual = self._check_expression(expression.arguments[0])
        expected = "String" if name == "parse_json" else "Data"
        self._require_assignable(
            (expected,), actual, f"{name}() argümanı", expression.location
        )
        return "Data or Error" if name == "parse_json" else "String or Error"

    try:
        return _ORIGINAL_CHECK_EXPRESSION(self, expression)
    except _semantic.SemanticError as error:
        if error.code != "KS3608":
            raise
        raise _semantic.SemanticError(
            "KS3708", error.message, error.location
        ) from error


def _check_statement(self, statement):
    # Unlike legacy fallible APIs, Data does not allow an unchecked Error union
    # to be hidden in a local variable. The caller must choose an `or` policy.
    if isinstance(statement, LetStatement) and _is_data_call(statement.value):
        self._check_expression(statement.value)
        raise _semantic.SemanticError(
            "KS1401",
            "Data çağrısı hata döndürebilir; 'or return', 'or varsayılan' "
            "veya 'or { ... }' ile açıkça ele alınmalıdır.",
            statement.location,
        )
    return _ORIGINAL_CHECK_STATEMENT(self, statement)


def _invoke(self, callee, arguments, location):
    result = _ORIGINAL_INVOKE(self, callee, arguments, location)
    if (
        isinstance(callee, str)
        and callee in ("parse_json", "encode_json")
        and isinstance(result, _runtime.KsError)
    ):
        return _runtime.KsError(_public_code(result.message))
    return result


def _register_public_diagnostics() -> None:
    from . import runtime_budget
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    # Data was installed before runtime_budget during package import. Restore the
    # established execution-budget meanings of KS3601 and KS3602. Other KS360x
    # entries document the internal codec core; user programs receive KS370x.
    for code in ("KS3601", "KS3602"):
        CATALOG.pop(code, None)
        ENGLISH_CATALOG.pop(code, None)
    runtime_budget._register_diagnostics()

    descriptions = {
        "KS3701": ("JSON girdi boyutu aşıldı", "JSON input byte limit exceeded"),
        "KS3702": ("JSON derinlik sınırı aşıldı", "JSON depth limit exceeded"),
        "KS3703": ("JSON düğüm sınırı aşıldı", "JSON node limit exceeded"),
        "KS3704": ("Yinelenen JSON anahtarı", "Duplicate JSON object key"),
        "KS3705": ("Geçersiz JSON", "Invalid JSON"),
        "KS3707": ("JSON çıktı boyutu aşıldı", "JSON output byte limit exceeded"),
        "KS3708": (
            "Data kodlama sözleşmesi ihlali",
            "Data encoding contract violation",
        ),
    }
    for code, (tr, en) in descriptions.items():
        CATALOG[code] = Diagnostic(
            code,
            tr,
            tr + ".",
            "Data ABI işlemi fail-closed reddedildi.",
            "Girdiyi veya kaynak bütçesini düzeltin.",
            'let data = parse_json("null") or return',
        )
        ENGLISH_CATALOG[code] = Diagnostic(
            code,
            en,
            en + ".",
            "The Data ABI operation failed closed.",
            "Fix the input or resource budget.",
            'let data = parse_json("null") or return',
        )


def install_data_public_abi_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_EXPRESSION, _ORIGINAL_CHECK_STATEMENT
    global _ORIGINAL_INVOKE
    if _INSTALLED:
        return
    _ORIGINAL_CHECK_EXPRESSION = _semantic.SemanticChecker._check_expression
    _ORIGINAL_CHECK_STATEMENT = _semantic.SemanticChecker._check_statement
    _ORIGINAL_INVOKE = _runtime.Interpreter._invoke
    _semantic.SemanticChecker._check_expression = _check_expression
    _semantic.SemanticChecker._check_statement = _check_statement
    _runtime.Interpreter._invoke = _invoke
    _register_public_diagnostics()
    _INSTALLED = True
