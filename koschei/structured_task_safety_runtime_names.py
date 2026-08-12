"""Expose task cancellation builtin names to AST-compatible sealed execution."""

from __future__ import annotations

from . import interpreter as _runtime
from .ast_nodes import Identifier

_CANCEL_BUILTINS = frozenset({"task_cancel", "task_cancel_all"})
_INSTALLED = False
_ORIGINAL_EVALUATE = None


def _evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in _CANCEL_BUILTINS:
        return expression.name
    return _ORIGINAL_EVALUATE(self, expression)


def install_structured_task_safety_runtime_names() -> None:
    global _INSTALLED, _ORIGINAL_EVALUATE
    if _INSTALLED:
        return
    _ORIGINAL_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _evaluate
    _INSTALLED = True
