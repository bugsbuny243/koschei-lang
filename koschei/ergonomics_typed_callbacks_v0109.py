"""Compatibility bridge for pre-v0.10.9 named-callback List methods.

Function identifiers now carry structural ``Fn<...>`` evidence.  ``find`` and
``filter`` previously treated a predicate argument as if its type were merely
the function's Bool return.  This bridge upgrades both methods to the same exact
``fn(T) -> Bool`` contract used by ``List.map``.
"""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import semantic
from .ergonomics_list_map_v0109 import (
    _instantiate_callback,
    _require_one_argument,
)
from .type_contracts import require_assignable
from .type_system import BOOL, GenericType, UnknownType, generic, is_named

_INSTALLED = False


def _typed_method(receiver, method, arguments, location):
    if method not in {"find", "filter"}:
        return _typed_method.original(receiver, method, arguments, location)

    _require_one_argument(arguments, location)
    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UnknownType()
    elif is_named(receiver, "List"):
        item = UnknownType()
    else:
        return _typed_method.original(receiver, method, arguments, location)

    parameter, result = _instantiate_callback(arguments[0], item, location)
    require_assignable(
        BOOL,
        result,
        f"List.{method}() predicate dönüş tipi",
        location,
    )
    if method == "find":
        return generic("Option", item)
    return receiver if isinstance(receiver, GenericType) else generic("List", parameter)


def install_typed_callbacks_v0109() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _typed_method.original = typed_ops.method_type
    typed_ops.method_type = _typed_method
    typed_expr.method_type = _typed_method
    _INSTALLED = True
