"""Direct-MIR adapter for the exact financial Decimal ABI."""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .financial_decimal import DecimalValue, FinancialDecimalError, decimal_text
from .financial_decimal_v1 import SIGNATURES, call_decimal

_BUILTINS = frozenset(SIGNATURES)
_INSTALLED = False
_ORIGINAL_INVOKE = None
_ORIGINAL_TO_STRING = None


def _invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name in _BUILTINS:
        expected = len(SIGNATURES[callee.name][0])
        if len(arguments) != expected:
            raise _mir.MirNativeRuntimeError(
                f"{callee.name} expects {expected} arguments"
            )
        try:
            return call_decimal(callee.name, arguments)
        except (FinancialDecimalError, TypeError, ValueError) as error:
            return _mir._ErrorValue(str(error))
    return _ORIGINAL_INVOKE(self, callee, arguments)


def _to_string(value):
    if isinstance(value, DecimalValue):
        return decimal_text(value)
    return _ORIGINAL_TO_STRING(value)


def install_financial_decimal_mir_v1() -> None:
    global _INSTALLED, _ORIGINAL_INVOKE, _ORIGINAL_TO_STRING
    if _INSTALLED:
        return
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | set(_BUILTINS))
    _ORIGINAL_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _invoke
    _ORIGINAL_TO_STRING = _mir._to_string
    _mir._to_string = _to_string
    _INSTALLED = True
