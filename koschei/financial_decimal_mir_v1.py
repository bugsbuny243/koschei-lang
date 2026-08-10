"""Direct-MIR adapter for the exact financial Decimal ABI."""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .financial_decimal import (
    DecimalValue,
    FinancialDecimalError,
    add_decimal,
    compare_decimal,
    decimal_text,
    parse_decimal,
    sub_decimal,
)

_BUILTINS = frozenset(
    {"decimal", "decimal_add", "decimal_sub", "decimal_cmp", "decimal_text"}
)
_INSTALLED = False
_ORIGINAL_INVOKE = None
_ORIGINAL_TO_STRING = None


def _invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name in _BUILTINS:
        expected = {
            "decimal": 2,
            "decimal_add": 2,
            "decimal_sub": 2,
            "decimal_cmp": 2,
            "decimal_text": 1,
        }[callee.name]
        if len(arguments) != expected:
            raise _mir.MirNativeRuntimeError(
                f"{callee.name} expects {expected} arguments"
            )
        try:
            if callee.name == "decimal":
                return parse_decimal(arguments[0], arguments[1])
            if callee.name == "decimal_add":
                return add_decimal(arguments[0], arguments[1])
            if callee.name == "decimal_sub":
                return sub_decimal(arguments[0], arguments[1])
            if callee.name == "decimal_cmp":
                return compare_decimal(arguments[0], arguments[1])
            if callee.name == "decimal_text":
                return decimal_text(arguments[0])
        except (FinancialDecimalError, TypeError, ValueError) as error:
            return _mir._ErrorValue(str(error))
        raise AssertionError(callee.name)
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
