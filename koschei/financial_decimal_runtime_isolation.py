"""Keep the Decimal interpreter ABI isolated from non-Decimal call dispatch.

The Decimal bridge is intentionally additive. Existing Koschei runtime values may
be unhashable (for example collections), so they must never be tested for
membership in the Decimal builtin-name set. This adapter routes only explicit
Decimal builtin names into the Decimal bridge and sends every other value
straight to the pre-Decimal interpreter dispatch chain.
"""

from __future__ import annotations

from . import financial_decimal_v1 as _decimal
from . import interpreter as _runtime

_INSTALLED = False


def _invoke(self, callee, arguments, expression):
    if isinstance(callee, str) and callee in _decimal._BUILTINS:
        return _decimal._runtime_invoke(self, callee, arguments, expression)
    return _decimal._ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, expression)


def install_financial_decimal_runtime_isolation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if _decimal._ORIGINAL_RUNTIME_INVOKE is None:
        raise RuntimeError("financial Decimal ABI must be installed before runtime isolation")
    _runtime.Interpreter._invoke = _invoke
    _INSTALLED = True
