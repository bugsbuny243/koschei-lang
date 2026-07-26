"""V5 runtime/type alignment bridge.

This module closes the temporary gap between structural Typed HIR contracts and
v0.9's defensive runtime checks. It is deliberately isolated so the bridge can
be deleted when the interpreter and native runtime consume Typed HIR directly.
"""

from __future__ import annotations

from typing import Any

from . import codegen_go as _codegen
from . import interpreter as _runtime
from .semantic import CAPABILITY_TYPES, INT_MIN
from .type_system import (
    GenericType,
    NamedType,
    TypeNode,
    UnionType,
    UnknownType,
    contains_named,
    generic,
    parse_type_text,
    render_type,
    union_type,
)

_INSTALLED = False
_ORIGINAL_EVALUATE = None


def _expected_type(expected_names) -> TypeNode:
    return union_type(*(parse_type_text(name) for name in expected_names))


def _runtime_type_node(value: Any) -> TypeNode:
    if value is _runtime.KsUnit:
        return NamedType("Void")
    if isinstance(value, _runtime.StructValue):
        return NamedType(value.type_name)
    if isinstance(value, _runtime.EnumValue):
        payload = (
            UnknownType()
            if value.payload is _runtime._NO_PAYLOAD
            else _runtime_type_node(value.payload)
        )
        if value.enum_name == "Option":
            return generic("Option", payload)
        if value.enum_name == "Result":
            if value.variant == "Ok":
                return generic("Result", payload, UnknownType())
            return generic("Result", UnknownType(), payload)
        return NamedType(value.enum_name)
    if isinstance(value, _runtime.KsError):
        return NamedType("Error")
    if isinstance(value, bool):
        return NamedType("Bool")
    if isinstance(value, str):
        return NamedType("String")
    if isinstance(value, float):
        return NamedType("Float")
    if isinstance(value, int):
        return NamedType("Int")
    if isinstance(value, list):
        return generic(
            "List", union_type(*(_runtime_type_node(item) for item in value))
        )
    if isinstance(value, dict):
        return generic(
            "Map",
            union_type(*(_runtime_type_node(key) for key in value.keys())),
            union_type(*(_runtime_type_node(item) for item in value.values())),
        )

    runtime_types = (
        (_runtime.SystemCaps, "SystemCaps"),
        (_runtime.NetRoot, "NetRoot"),
        (_runtime.DiskRoot, "DiskRoot"),
        (_runtime.EnvRoot, "EnvRoot"),
        (_runtime.ProcessRoot, "ProcessRoot"),
        (_runtime.NetCaps, "NetCaps"),
        (_runtime.DiskCaps, "DiskCaps"),
        (_runtime.DiskReadCaps, "DiskReadCaps"),
        (_runtime.EnvCaps, "EnvCaps"),
        (_runtime.ProcessCaps, "ProcessCaps"),
        (_runtime.Response, "Response"),
    )
    for runtime_type, name in runtime_types:
        if isinstance(value, runtime_type):
            return NamedType(name)
    return NamedType(type(value).__name__)


def _matches_node(value: Any, expected: TypeNode) -> bool:
    if isinstance(expected, UnknownType):
        return True
    if isinstance(expected, UnionType):
        return any(_matches_node(value, option) for option in expected.options)
    if isinstance(expected, NamedType):
        if expected.name == "List":
            return isinstance(value, list)
        if expected.name == "Map":
            return isinstance(value, dict)
        if expected.name in {"Option", "Result"}:
            return (
                isinstance(value, _runtime.EnumValue)
                and value.enum_name == expected.name
            )
        return _runtime_type_node(value) == expected
    if isinstance(expected, GenericType):
        if expected.name == "Option" and len(expected.arguments) == 1:
            if (
                not isinstance(value, _runtime.EnumValue)
                or value.enum_name != "Option"
            ):
                return False
            if value.variant == "None":
                return True
            return (
                value.variant == "Some"
                and value.payload is not _runtime._NO_PAYLOAD
                and _matches_node(value.payload, expected.arguments[0])
            )
        if expected.name == "Result" and len(expected.arguments) == 2:
            if (
                not isinstance(value, _runtime.EnumValue)
                or value.enum_name != "Result"
                or value.payload is _runtime._NO_PAYLOAD
            ):
                return False
            if value.variant == "Ok":
                return _matches_node(value.payload, expected.arguments[0])
            if value.variant == "Err":
                return _matches_node(value.payload, expected.arguments[1])
            return False
        if expected.name == "List" and len(expected.arguments) == 1:
            return isinstance(value, list) and all(
                _matches_node(item, expected.arguments[0]) for item in value
            )
        if expected.name == "Map" and len(expected.arguments) == 2:
            return isinstance(value, dict) and all(
                _matches_node(key, expected.arguments[0])
                and _matches_node(item, expected.arguments[1])
                for key, item in value.items()
            )
    return False


def _runtime_matches_type(self, value: Any, expected_names) -> bool:
    return _matches_node(value, _expected_type(expected_names))


def _runtime_type_name(cls, value: Any) -> str:
    return render_type(_runtime_type_node(value))


def _raise_runtime_contract_error(
    self,
    subject: str,
    expected_names,
    value: Any,
    location,
) -> None:
    expected = _expected_type(expected_names)
    actual = _runtime_type_node(value)
    capability_related = (
        contains_named(expected, CAPABILITY_TYPES)
        or contains_named(actual, CAPABILITY_TYPES)
        or _runtime._contains_capability(value)
    )
    if capability_related:
        raise _runtime.KoscheiRuntimeError(
            "KS3401",
            f"{subject} {render_type(expected)} beklerken "
            f"{render_type(actual)} aldı; runtime capability type-integrity "
            "savunması yetki gizleme/yanlış türleme girişimini reddetti.",
            location,
        )
    raise _runtime.KoscheiRuntimeError(
        "KS3106",
        f"{subject} {render_type(expected)} beklerken "
        f"{render_type(actual)} aldı. Bu normal bir runtime tip sözleşmesi "
        "uyuşmazlığıdır; capability ihlali değildir.",
        location,
    )


def _call_function(
    self,
    function,
    arguments: list[Any],
    namespace=None,
    imports=None,
) -> Any:
    if len(arguments) != len(function.parameters):
        raise _runtime.KoscheiRuntimeError(
            "KS3101",
            f"'{function.name}' için {len(function.parameters)} argüman bekleniyor, "
            f"{len(arguments)} verildi.",
            function.location,
        )

    for parameter, value in zip(function.parameters, arguments):
        if not self._runtime_matches_type(value, parameter.type_ref.names):
            self._raise_runtime_contract_error(
                f"'{function.name}' çağrısında '{parameter.name}' parametresi",
                parameter.type_ref.names,
                value,
                parameter.location,
            )

    if self._depth >= self.MAX_CALL_DEPTH:
        raise _runtime.KoscheiRuntimeError(
            "KS3105",
            f"Çağrı derinliği sınırı aşıldı ({self.MAX_CALL_DEPTH}); "
            "sonsuz özyineleme olabilir.",
            function.location,
        )

    previous = self.environment
    previous_functions = self.functions
    previous_imports = self.imports
    self.environment = _runtime._Environment()
    if namespace is not None:
        self.functions = namespace
    if imports is not None:
        self.imports = imports
    self._depth += 1
    try:
        for parameter, value in zip(function.parameters, arguments):
            self.environment.define(parameter.name, value, False)
        try:
            result = self._execute_block(function.body, create_scope=False)
        except _runtime._ReturnSignal as signal:
            result = signal.value

        if (
            function.return_type is not None
            and not self._runtime_matches_type(result, function.return_type.names)
        ):
            self._raise_runtime_contract_error(
                f"'{function.name}' dönüş değeri",
                function.return_type.names,
                result,
                function.location,
            )
        return result
    finally:
        self._depth -= 1
        self.environment = previous
        self.functions = previous_functions
        self.imports = previous_imports


def _binary(self, expression) -> Any:
    left = self._evaluate(expression.left)
    if isinstance(left, _runtime.KsError):
        return left
    if expression.operator == "&&":
        if not bool(left):
            return False
        right = self._evaluate(expression.right)
        return right if isinstance(right, _runtime.KsError) else bool(right)
    if expression.operator == "||":
        if bool(left):
            return True
        right = self._evaluate(expression.right)
        return right if isinstance(right, _runtime.KsError) else bool(right)

    right = self._evaluate(expression.right)
    if isinstance(right, _runtime.KsError):
        return right
    operator = expression.operator
    if operator in {"+", "-", "*"} and type(left) is int and type(right) is int:
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        else:
            result = left * right
        if not _runtime.INT_MIN <= result <= _runtime.INT_MAX:
            return self._int_overflow(operator)
        return result
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "/":
        if right == 0:
            return _runtime.KsError("Sıfıra bölme")
        if type(left) is int and type(right) is int:
            if left == INT_MIN and right == -1:
                return self._int_overflow("/")
            quotient = abs(left) // abs(right)
            return -quotient if (left < 0) != (right < 0) else quotient
        return left / right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    raise AssertionError(operator)


def _reclassify_runtime_error(error):
    if error.code != "KS3401":
        return error
    message = error.message
    security_markers = (
        "Capability taşıyan",
        "type-laundering",
        "SystemCaps",
        *tuple(CAPABILITY_TYPES),
    )
    if any(marker in message for marker in security_markers):
        return error
    return _runtime.KoscheiRuntimeError(
        "KS3106",
        f"{message} Bu normal bir runtime tip sözleşmesi uyuşmazlığıdır; "
        "capability ihlali değildir.",
        error.location,
    )


def _evaluate(self, expression):
    try:
        return _ORIGINAL_EVALUATE(self, expression)
    except _runtime.KoscheiRuntimeError as error:
        converted = _reclassify_runtime_error(error)
        if converted is error:
            raise
        raise converted from error


def _patch_native_division() -> None:
    old = "\t\t\treturn float64(a) / float64(b)\n"
    new = (
        "\t\t\tif a == ksIntMin && b == -1 {\n"
        "\t\t\t\treturn ksIntOverflow(\"/\")\n"
        "\t\t\t}\n"
        "\t\t\treturn a / b\n"
    )
    if old in _codegen.RUNTIME_PRELUDE:
        _codegen.RUNTIME_PRELUDE = _codegen.RUNTIME_PRELUDE.replace(old, new, 1)
    elif new not in _codegen.RUNTIME_PRELUDE:
        raise RuntimeError("Koschei native division ABI changed; alignment patch refused")


def _register_diagnostic() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG.setdefault(
        "KS3106",
        Diagnostic(
            "KS3106",
            "Runtime tip sözleşmesi uyuşmazlığı",
            "Runtime bildirilen tipten farklı bir değer gördü.",
            "Statik denetim bunu normalde önce yakalar; bu savunma katmanı backend "
            "ayrışmasını yakalar ve capability saldırılarından ayrı raporlar.",
            "Bildirilen tip ile üretilen değeri eşleştirin ve önce 'ks check' çalıştırın.",
            "fn percent(value: Int) -> Int { return value * 20 / 100 }",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3106",
        Diagnostic(
            "KS3106",
            "Runtime type-contract mismatch",
            "The runtime observed a value that does not satisfy its declared type.",
            "Static analysis normally catches this first; the defensive runtime layer "
            "reports backend divergence separately from capability attacks.",
            "Make the declared type match the produced value and run 'ks check' first.",
            "fn percent(value: Int) -> Int { return value * 20 / 100 }",
        ),
    )


def install_runtime_alignment() -> None:
    global _INSTALLED, _ORIGINAL_EVALUATE
    if _INSTALLED:
        return
    _ORIGINAL_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._runtime_matches_type = _runtime_matches_type
    _runtime.Interpreter._runtime_type_name = classmethod(_runtime_type_name)
    _runtime.Interpreter._raise_runtime_contract_error = _raise_runtime_contract_error
    _runtime.Interpreter._call_function = _call_function
    _runtime.Interpreter._binary = _binary
    _runtime.Interpreter._evaluate = _evaluate
    _patch_native_division()
    _register_diagnostic()
    _INSTALLED = True
