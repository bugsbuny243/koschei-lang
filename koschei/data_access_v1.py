"""Reading JSON ``Data`` and quoting JSON text (``koschei.data-json/v1``).

``parse_json`` returns an opaque ``Data``. These methods read it without
exposing the host representation, in every executor and in native binaries:

=================  ==========================================================
``kind()``         ``String``: object, array, string, number, bool or null
``get(key)``       ``Data or Error``: an object's member
``at(index)``      ``Data or Error``: an array's item, counted from 0
``length()``       ``Int or Error``: an array's items or an object's members
``keys()``         ``List<String> or Error``: an object's keys, by code point
``text()``         ``String or Error``: a string
``number()``       ``String or Error``: a number's canonical text
``int()``          ``Int or Error``: an integer number in the signed 64-bit range
``bool()``         ``Bool or Error``
``is_null()``      ``Bool``
=================  ==========================================================

A value of the wrong kind, a missing key or index and a number that is not an
Int are ``KS3709`` Error values. ``json_quote(text)`` returns the JSON string
literal for a String, escaped exactly as ``encode_json`` writes strings, so a
program can build JSON text without hand-written escaping. Its result obeys
the 16 MiB String budget (``KS3502``).

``parse_json`` and ``encode_json`` report the public ``KS370x`` codes in every
executor; the shared codec core numbers them ``KS360x``.
"""

from __future__ import annotations

import re
from typing import Any

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from . import _typed_expr
from . import _typed_ops
from .ast_nodes import CallExpression, Identifier
from .data_json_v1 import Number, quote
from .data_language_v1 import DataValue
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .type_system import BOOL, ERROR, INT, STRING, GenericType, NamedType, union_type
from .value_budget_v1 import MAX_STRING_BYTES, STRING_MESSAGE

QUOTE = "json_quote"
CODEC_BUILTINS = frozenset({"parse_json", "encode_json"})
DATA = NamedType("Data")

KIND_MESSAGE = "KS3709: JSON değeri {expected} değil: {actual}"
MISSING_MESSAGE = "KS3709: JSON nesnesinde {key} anahtarı yok"
INDEX_MESSAGE = "KS3709: JSON dizisinde {index} indeksi yok (uzunluk {length})"
INT_MESSAGE = "KS3709: JSON sayısı Int değil: {number}"
CONTAINER = "array ya da object"

# name: (argument types, legacy result type)
METHODS: dict[str, tuple[tuple[str, ...], str]] = {
    "kind": ((), "String"),
    "get": (("String",), "Data or Error"),
    "at": (("Int",), "Data or Error"),
    "length": ((), "Int or Error"),
    "keys": ((), "List<String> or Error"),
    "text": ((), "String or Error"),
    "number": ((), "String or Error"),
    "int": ((), "Int or Error"),
    "bool": ((), "Bool or Error"),
    "is_null": ((), "Bool"),
}
_TYPED_ARGUMENTS = {"get": (STRING,), "at": (INT,)}
_TYPED_RESULTS = {
    "kind": STRING,
    "get": union_type(DATA, ERROR),
    "at": union_type(DATA, ERROR),
    "length": union_type(INT, ERROR),
    "keys": union_type(GenericType("List", (STRING,)), ERROR),
    "text": union_type(STRING, ERROR),
    "number": union_type(STRING, ERROR),
    "int": union_type(INT, ERROR),
    "bool": union_type(BOOL, ERROR),
    "is_null": BOOL,
}
_FALLIBLE = frozenset(name for name, (_, result) in METHODS.items() if result.endswith("or Error"))
_INT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_INT64 = (-(2**63), 2**63 - 1)

_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


# ---- the operations, shared by every Python executor -----------------------


def public_message(message: str) -> str:
    """The codec core numbers its failures KS360x; programs see KS370x."""

    return "KS37" + message[4:] if message.startswith("KS36") else message


def kind_of(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "bool"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Number):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise AssertionError(type(value).__name__)


def _wrong(expected: str, value: Any) -> _runtime.KsError:
    return _runtime.KsError(KIND_MESSAGE.format(expected=expected, actual=kind_of(value)))


def data_method(receiver: DataValue, name: str, arguments: list[Any]) -> Any:
    value = receiver.value
    kind = kind_of(value)
    if name == "kind":
        return kind
    if name == "is_null":
        return value is None
    if name == "get":
        (key,) = arguments
        if kind != "object":
            return _wrong("object", value)
        if key not in value:
            return _runtime.KsError(MISSING_MESSAGE.format(key=quote(key)))
        return DataValue(value[key])
    if name == "at":
        (index,) = arguments
        if kind != "array":
            return _wrong("array", value)
        if not 0 <= index < len(value):
            return _runtime.KsError(INDEX_MESSAGE.format(index=index, length=len(value)))
        return DataValue(value[index])
    if name == "length":
        if kind not in ("array", "object"):
            return _wrong(CONTAINER, value)
        return len(value)
    if name == "keys":
        if kind != "object":
            return _wrong("object", value)
        return sorted(value)
    if name == "text":
        return value if kind == "string" else _wrong("string", value)
    if name == "number":
        return value.text if kind == "number" else _wrong("number", value)
    if name == "int":
        if kind != "number":
            return _wrong("number", value)
        if _INT.match(value.text) and _INT64[0] <= int(value.text) <= _INT64[1]:
            return int(value.text)
        return _runtime.KsError(INT_MESSAGE.format(number=value.text))
    if name == "bool":
        return value if kind == "bool" else _wrong("bool", value)
    raise AssertionError(name)


def json_quote(value: Any) -> Any:
    if not isinstance(value, str):
        return _runtime.KsError("KS3708: json_quote() String bekler")
    quoted = quote(value)
    if len(quoted.encode("utf-8")) > MAX_STRING_BYTES:
        return _runtime.KsError(STRING_MESSAGE)
    return quoted


# ---- legacy checker ---------------------------------------------------------


def _is_quote_call(expression) -> bool:
    return (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name == QUOTE
    )


def _semantic_expression(self, expression):
    if _is_quote_call(expression):
        if len(expression.arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301",
                f"'{QUOTE}' 1 argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        actual = self._check_expression(expression.arguments[0])
        self._require_assignable(("String",), actual, f"'{QUOTE}' argümanı", expression.location)
        return "String or Error"
    return _ORIGINALS["semantic_expression"](self, expression)


def _semantic_fallible(self, expression):
    if _is_quote_call(expression):
        return True
    callee = getattr(expression, "callee", None)
    if isinstance(expression, CallExpression) and hasattr(callee, "member"):
        if callee.member in _FALLIBLE and self._receiver_type(callee.object) == "Data":
            return True
    return _ORIGINALS["semantic_fallible"](self, expression)


def _semantic_receiver(self, expression):
    if _is_quote_call(expression):
        return "String or Error"
    return _ORIGINALS["semantic_receiver"](self, expression)


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    if receiver_type != "Data":
        return _ORIGINALS["check_method_call"](
            self, receiver_type, method_name, location, argument_types, arguments
        )
    operation = METHODS.get(method_name)
    if operation is None:
        raise _semantic.SemanticError(
            "KS1502",
            f"Data üzerinde '{method_name}' metodu yok. Kullanılabilir: {', '.join(sorted(METHODS))}.",
            location,
        )
    expected, result = operation
    values = argument_types or []
    if len(values) != len(expected):
        raise _semantic.SemanticError(
            "KS1301",
            f"Data.{method_name}() {len(expected)} argüman bekler, {len(values)} verildi.",
            location,
        )
    for accepted, value in zip(expected, values):
        self._require_assignable((accepted,), value, f"Data.{method_name}() argümanı", location)
    return result


# ---- Typed HIR --------------------------------------------------------------


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType) and receiver.name == "Data":
        if method not in METHODS:
            raise _semantic.SemanticError(
                "KS1306", f"'{method}' işlemi Data tipi için güvenli değildir.", location
            )
        expected = _TYPED_ARGUMENTS.get(method, ())
        if len(arguments) != len(expected):
            raise _semantic.SemanticError(
                "KS1301",
                f"Data.{method}() {len(expected)} argüman bekler, {len(arguments)} verildi.",
                location,
            )
        for accepted, argument in zip(expected, arguments):
            _contracts.require_assignable(accepted, argument, f"Data.{method}() argümanı", location)
        return _TYPED_RESULTS[method]
    return _ORIGINALS["method_type"](receiver, method, arguments, location)


def _typed_call_type(self, name, arguments, location):
    if name == QUOTE:
        if len(arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301", f"'{QUOTE}' 1 argüman bekler, {len(arguments)} verildi.", location
            )
        _contracts.require_assignable(STRING, arguments[0], f"'{QUOTE}' argümanı", location)
        return union_type(STRING, ERROR)
    return _ORIGINALS["typed_call_type"](self, name, arguments, location)


# ---- runtimes ---------------------------------------------------------------


def _runtime_member(self, receiver, name, location):
    if isinstance(receiver, DataValue) and name in METHODS:
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINALS["runtime_member"](self, receiver, name, location)


def _runtime_invoke_member(self, member, arguments):
    if isinstance(member.receiver, DataValue) and member.name in METHODS:
        self._require_arity(member.name, arguments, len(METHODS[member.name][0]), member.location)
        return data_method(member.receiver, member.name, arguments)
    return _ORIGINALS["runtime_invoke_member"](self, member, arguments)


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name == QUOTE:
        return QUOTE
    return _ORIGINALS["runtime_evaluate"](self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if callee == QUOTE:
        self._require_arity(QUOTE, arguments, 1, location)
        return json_quote(arguments[0])
    return _ORIGINALS["runtime_invoke"](self, callee, arguments, location)


def _facade_member_allowed(cls, member):
    if isinstance(member.receiver, DataValue):
        return member.name in METHODS
    return _ORIGINALS["facade_member_allowed"].__func__(cls, member)


def _mir_invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef):
        if callee.name == QUOTE:
            if len(arguments) != 1:
                raise _mir.MirNativeRuntimeError(f"{QUOTE} expects one argument")
            result = json_quote(arguments[0])
            return _mir._ErrorValue(result.message) if isinstance(result, _runtime.KsError) else result
        if callee.name in CODEC_BUILTINS:
            result = _ORIGINALS["mir_invoke"](self, callee, arguments)
            if isinstance(result, _mir._ErrorValue):
                return _mir._ErrorValue(public_message(result.message))
            return result
    return _ORIGINALS["mir_invoke"](self, callee, arguments)


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    example = 'let name = data.get("name") or return\nlet text = name.text() or return'
    CATALOG["KS3709"] = Diagnostic(
        "KS3709",
        "JSON değeri beklenen biçimde değil",
        "Bir Data metodu yanlış türde bir JSON değerinde, olmayan bir anahtarda veya "
        "indekste ya da Int olmayan bir sayıda çağrıldı.",
        "JSON girdisi dışarıdan gelir; her okuma hatası açık bir hata değeridir, sessiz bir varsayılan değildir.",
        "Önce kind() ile türü denetleyin ya da hatayı 'or' ile ele alın.",
        example,
    )
    ENGLISH_CATALOG["KS3709"] = Diagnostic(
        "KS3709",
        "JSON value has the wrong shape",
        "A Data method was called on a JSON value of the wrong kind, a missing key or index, "
        "or a number that is not an Int.",
        "JSON input comes from outside; every failed read is an explicit Error value, never a silent default.",
        "Check the kind with kind() first, or handle the Error with 'or'.",
        example,
    )


def install_data_access_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.add(QUOTE)
    _effects._PURE_BUILTINS.add(QUOTE)
    _effects._PURE_VALUE_METHODS.update(METHODS)
    _ORIGINALS["semantic_expression"] = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINALS["semantic_fallible"] = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINALS["semantic_receiver"] = _semantic.SemanticChecker._receiver_type
    _semantic.SemanticChecker._receiver_type = _semantic_receiver
    _ORIGINALS["check_method_call"] = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call

    _ORIGINALS["method_type"] = _typed_ops.method_type
    _typed_ops.method_type = _method_type
    _typed_expr.method_type = _method_type
    _ORIGINALS["typed_call_type"] = _typed_hir.TypedHIRChecker.call_type
    _typed_hir.TypedHIRChecker.call_type = _typed_call_type

    # Checked-AST interpreter; the canonical MIR executor reaches the same
    # operations through the runtime primitive facade.
    _ORIGINALS["runtime_member"] = _runtime.Interpreter._member
    _runtime.Interpreter._member = _runtime_member
    _ORIGINALS["runtime_invoke_member"] = _runtime.Interpreter._invoke_member
    _runtime.Interpreter._invoke_member = _runtime_invoke_member
    _ORIGINALS["runtime_evaluate"] = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINALS["runtime_invoke"] = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke
    RuntimePrimitiveFacadeV1._BUILTIN_CALLS = frozenset(
        RuntimePrimitiveFacadeV1._BUILTIN_CALLS | CODEC_BUILTINS | {QUOTE}
    )
    _ORIGINALS["facade_member_allowed"] = RuntimePrimitiveFacadeV1.__dict__["_member_allowed"]
    RuntimePrimitiveFacadeV1._member_allowed = classmethod(_facade_member_allowed)

    # Direct MIR runtime: no Data methods (it does not admit value members),
    # but the same builtins and public codes.
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | {QUOTE})
    _ORIGINALS["mir_invoke"] = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke

    _register_diagnostics()
    _INSTALLED = True


__all__ = [
    "INDEX_MESSAGE",
    "INT_MESSAGE",
    "KIND_MESSAGE",
    "METHODS",
    "MISSING_MESSAGE",
    "QUOTE",
    "data_method",
    "install_data_access_v1",
    "json_quote",
    "kind_of",
    "public_message",
]
