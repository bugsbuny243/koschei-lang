"""Keep the Decimal interpreter ABI isolated from non-Decimal call dispatch.

The Decimal bridge is intentionally additive. Existing Koschei runtime values may
be unhashable (for example collections), so they must never be tested for
membership in the Decimal builtin-name set. This adapter routes only explicit
Decimal builtin names into Decimal helpers and preserves the interpreter's
``SourceLocation`` call contract for every path.
"""

from __future__ import annotations

from . import financial_decimal_v1 as _decimal
from . import interpreter as _runtime

_INSTALLED = False


def _invoke(self, callee, arguments, location):
    if not (isinstance(callee, str) and callee in _decimal._BUILTINS):
        return _decimal._ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)

    expected = {
        "decimal": 2,
        "decimal_add": 2,
        "decimal_sub": 2,
        "decimal_cmp": 2,
        "decimal_text": 1,
    }[callee]
    self._require_arity(callee, arguments, expected, location)
    try:
        if callee == "decimal":
            return _decimal.parse_decimal(arguments[0], arguments[1])
        if callee == "decimal_add":
            return _decimal.add_decimal(arguments[0], arguments[1])
        if callee == "decimal_sub":
            return _decimal.sub_decimal(arguments[0], arguments[1])
        if callee == "decimal_cmp":
            return _decimal.compare_decimal(arguments[0], arguments[1])
        if callee == "decimal_text":
            return _decimal.decimal_text(arguments[0])
    except (_decimal.FinancialDecimalError, TypeError, ValueError) as error:
        return _runtime.KsError(str(error))
    raise AssertionError(callee)


def install_financial_decimal_runtime_isolation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if _decimal._ORIGINAL_RUNTIME_INVOKE is None:
        raise RuntimeError("financial Decimal ABI must be installed before runtime isolation")
    _runtime.Interpreter._invoke = _invoke
    _INSTALLED = True
