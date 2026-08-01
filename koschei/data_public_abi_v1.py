"""Public diagnostic boundary for the opaque Data language ABI.

The lower-level data-json/v1 cores predate the runtime-budget diagnostics and use
internal KS360x parser codes. The language ABI maps those implementation codes to
the dedicated KS370x range so one public code has exactly one meaning.
"""

from __future__ import annotations

from . import interpreter as _runtime
from . import semantic as _semantic

_INSTALLED = False
_ORIGINAL_CHECK_EXPRESSION = None
_ORIGINAL_INVOKE = None


def _public_code(text: str) -> str:
    if text.startswith("KS36"):
        return "KS37" + text[4:]
    return text


def _check_expression(self, expression):
    try:
        return _ORIGINAL_CHECK_EXPRESSION(self, expression)
    except _semantic.SemanticError as error:
        if error.code != "KS3608":
            raise
        raise _semantic.SemanticError(
            "KS3708", error.message, error.location
        ) from error


def _invoke(self, callee, arguments, location):
    result = _ORIGINAL_INVOKE(self, callee, arguments, location)
    if callee in {"parse_json", "encode_json"} and isinstance(
        result, _runtime.KsError
    ):
        return _runtime.KsError(_public_code(result.message))
    return result


def _register_public_diagnostics() -> None:
    from . import runtime_budget
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    # Data was installed before runtime_budget during package import. Restore the
    # established execution-budget meanings of KS3601 and KS3602. The remaining
    # KS360x entries describe the internal codec core and stay documented for
    # compiler-source integrity checks; user programs receive KS370x instead.
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
    global _INSTALLED, _ORIGINAL_CHECK_EXPRESSION, _ORIGINAL_INVOKE
    if _INSTALLED:
        return
    _ORIGINAL_CHECK_EXPRESSION = _semantic.SemanticChecker._check_expression
    _ORIGINAL_INVOKE = _runtime.Interpreter._invoke
    _semantic.SemanticChecker._check_expression = _check_expression
    _runtime.Interpreter._invoke = _invoke
    _register_public_diagnostics()
    _INSTALLED = True
