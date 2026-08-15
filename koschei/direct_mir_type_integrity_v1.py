"""Runtime type-integrity and checked-Int64 bridge for direct MIR v1.

The direct executor is intentionally smaller than the compatibility interpreter,
but values crossing a supported function boundary still must not escape the type
contract sealed into MIR. This bridge enforces the direct-native types that v1 can
prove structurally: Void, Bool, Int, Float, String, Error, Data and List<T>.
Unknown/custom aggregate types remain outside this bridge and are governed by the
existing direct-MIR support inspector until their native representation is sealed.
"""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .data_language_v1 import DataValue
from .semantic import INT_MAX, INT_MIN
from .type_system import (
    GenericType,
    NamedType,
    TypeVariable,
    UnionType,
    UnknownType,
    render_type,
)

_INSTALLED = False
_ORIGINAL_BINARY = None
_ORIGINAL_UNARY = None
_ORIGINAL_CALL = None


def _matches(value, expected) -> bool:
    if isinstance(expected, (UnknownType, TypeVariable)):
        return True
    if isinstance(expected, UnionType):
        return any(_matches(value, option) for option in expected.options)
    if isinstance(expected, GenericType):
        if expected.name == "List" and len(expected.arguments) == 1:
            return isinstance(value, tuple) and all(
                _matches(item, expected.arguments[0]) for item in value
            )
        # Direct representations for other generic aggregates are not sealed by
        # this v1 bridge. Their support gate remains authoritative.
        return True
    if not isinstance(expected, NamedType):
        return True

    name = expected.name
    if name == "Void":
        return value is _mir._UNIT
    if name == "Bool":
        return isinstance(value, bool)
    if name == "Int":
        return type(value) is int and INT_MIN <= value <= INT_MAX
    if name == "Float":
        return isinstance(value, float)
    if name == "String":
        return isinstance(value, str)
    if name == "Error":
        return isinstance(value, _mir._ErrorValue)
    if name == "Data":
        return isinstance(value, DataValue)
    if name == "List":
        return isinstance(value, tuple)

    # Custom named aggregates are not admitted as native-MIR structs/enums today.
    # Do not invent a host representation contract here.
    return True


def _contract_error(subject: str, expected, value) -> _mir.MirNativeRuntimeError:
    actual = type(value).__name__
    if isinstance(value, _mir._ErrorValue):
        actual = "Error"
    elif value is _mir._UNIT:
        actual = "Void"
    elif type(value) is int:
        actual = "Int"
    elif isinstance(value, bool):
        actual = "Bool"
    elif isinstance(value, str):
        actual = "String"
    elif isinstance(value, float):
        actual = "Float"
    elif isinstance(value, tuple):
        actual = "List"
    elif isinstance(value, DataValue):
        actual = "Data"
    return _mir.MirNativeRuntimeError(
        f"KS3106: {subject} expected {render_type(expected)}, got {actual}"
    )


def _call(self, function, arguments, module_key=None):
    active_module_key = module_key or self.current_module_key

    if len(arguments) == len(function.parameters):
        for parameter, value in zip(function.parameters, arguments, strict=True):
            if not _matches(value, parameter.type):
                raise _contract_error(
                    f"{function.name} parameter {parameter.name}",
                    parameter.type,
                    value,
                )

    result = _ORIGINAL_CALL(self, function, arguments, module_key)

    # Root main has an implicit process-error edge: run_mir_native converts a
    # returned Error into MirNativeProgramError after execution.
    if (
        function.name == "main"
        and active_module_key == self.mir.root
        and isinstance(result, _mir._ErrorValue)
    ):
        return result

    if not _matches(result, function.return_type):
        raise _contract_error(
            f"{function.name} return value",
            function.return_type,
            result,
        )
    return result


def _binary(operator, left, right):
    if isinstance(left, _mir._ErrorValue):
        return left
    if isinstance(right, _mir._ErrorValue):
        return right

    if operator in {"+", "-", "*"} and type(left) is int and type(right) is int:
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        else:
            result = left * right
        if not INT_MIN <= result <= INT_MAX:
            return _mir._ErrorValue(
                f"KS3501: Int overflow: '{operator}' exceeded signed 64-bit range"
            )
        return result

    return _ORIGINAL_BINARY(operator, left, right)


def _unary(operator, operand):
    if isinstance(operand, _mir._ErrorValue):
        return operand
    if operator == "-" and type(operand) is int and operand == INT_MIN:
        return _mir._ErrorValue(
            "KS3501: Int overflow: unary '-' exceeded signed 64-bit range"
        )
    return _ORIGINAL_UNARY(operator, operand)


def install_direct_mir_type_integrity_v1() -> None:
    global _INSTALLED, _ORIGINAL_BINARY, _ORIGINAL_UNARY, _ORIGINAL_CALL
    if _INSTALLED:
        return

    _ORIGINAL_BINARY = _mir._binary
    _mir._binary = _binary

    _ORIGINAL_UNARY = _mir._unary
    _mir._unary = _unary

    _ORIGINAL_CALL = _mir._MirExecutor._call
    _mir._MirExecutor._call = _call

    _INSTALLED = True
