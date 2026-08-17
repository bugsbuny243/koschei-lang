"""Direct-MIR adapter for bounded deterministic Data JSON v1."""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .data_json_v1 import DataError, decode, encode
from .data_language_v1 import DataValue

_BUILTINS = frozenset({"parse_json", "encode_json"})
_INSTALLED = False
_ORIGINAL_INVOKE = None
_ORIGINAL_TO_STRING = None


def _invoke(self, callee, arguments):
    if not (
        isinstance(callee, _mir._BuiltinRef)
        and callee.name in _BUILTINS
    ):
        return _ORIGINAL_INVOKE(self, callee, arguments)

    if len(arguments) != 1:
        raise _mir.MirNativeRuntimeError(
            f"{callee.name} expects one argument"
        )

    if callee.name == "parse_json":
        raw = arguments[0]
        if not isinstance(raw, str):
            return _mir._ErrorValue("KS3608: parse_json() String bekler")
        try:
            return DataValue(decode(raw))
        except DataError as error:
            return _mir._ErrorValue(str(error))

    value = arguments[0]
    if not isinstance(value, DataValue):
        return _mir._ErrorValue("KS3608: encode_json() Data bekler")
    try:
        return encode(value.value)
    except DataError as error:
        return _mir._ErrorValue(str(error))


def _to_string(value):
    if isinstance(value, DataValue):
        return "<data>"
    return _ORIGINAL_TO_STRING(value)


def install_data_mir_v1() -> None:
    global _INSTALLED, _ORIGINAL_INVOKE, _ORIGINAL_TO_STRING
    if _INSTALLED:
        return

    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | set(_BUILTINS))
    _ORIGINAL_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _invoke

    _ORIGINAL_TO_STRING = _mir._to_string
    _mir._to_string = _to_string

    _INSTALLED = True
