"""Argument checking for ``NetCaps.get`` and ``NetCaps.post`` (net_v1).

Both results stay dynamic (``Response`` or an Error value); what the checker
adds is the argument count and types, so that ``ks run`` and a native binary
never see a call they would treat differently:

* ``get(url: String)``
* ``post(url: String, content_type: String, body: String or Bytes)``
"""

from __future__ import annotations

from . import semantic as _semantic
from . import _typed_expr
from . import _typed_ops
from .type_system import STRING, NamedType, union_type

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None
_ORIGINAL_METHOD_TYPE = None

_ARGUMENTS = {
    "get": (("url", ("String",)),),
    "post": (
        ("url", ("String",)),
        ("content_type", ("String",)),
        ("body", ("String", "Bytes")),
    ),
}

_TYPED_ARGUMENTS = {
    "get": (STRING,),
    "post": (STRING, STRING, union_type(STRING, NamedType("Bytes"))),
}


def _arity(method_name, count, location):
    expected = len(_ARGUMENTS[method_name])
    if count != expected:
        raise _semantic.SemanticError(
            "KS1301",
            f"NetCaps.{method_name}() {expected} argüman bekler, {count} verildi.",
            location,
        )


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    if receiver_type == "NetCaps" and method_name in _ARGUMENTS:
        values = argument_types or []
        _arity(method_name, len(values), location)
        for (name, accepted), value in zip(_ARGUMENTS[method_name], values):
            self._require_assignable(accepted, value, f"NetCaps.{method_name}() {name}", location)
    return _ORIGINAL_CHECK_METHOD_CALL(self, receiver_type, method_name, location, argument_types, arguments)


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType) and receiver.name == "NetCaps" and method in _TYPED_ARGUMENTS:
        _arity(method, len(arguments), location)
        for (name, _accepted), expected, argument in zip(_ARGUMENTS[method], _TYPED_ARGUMENTS[method], arguments):
            _typed_ops.require_assignable(expected, argument, f"NetCaps.{method}() {name}", location)
    return _ORIGINAL_METHOD_TYPE(receiver, method, arguments, location)


def install_net_typing_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_METHOD_CALL, _ORIGINAL_METHOD_TYPE
    if _INSTALLED:
        return
    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call
    _ORIGINAL_METHOD_TYPE = _typed_ops.method_type
    _typed_ops.method_type = _method_type
    _typed_expr.method_type = _method_type
    _INSTALLED = True


__all__ = ["install_net_typing_v1"]
