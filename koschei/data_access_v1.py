"""Read access to opaque ``Data`` values (JSON) for Koschei programs.

``parse_json`` gives a program an opaque ``Data`` value. These kernel builtins
let it look inside without exposing the host representation:

    json_kind(data)        -> String             "object", "array", "string",
                                                  "number", "bool" or "null"
    json_has(data, key)    -> Bool               true for an object with key
    json_get(data, key)    -> Data or Error      object member
    json_at(data, index)   -> Data or Error      array element
    json_text(data)        -> String or Error    JSON string
    json_int(data)         -> Int or Error       integral number within Int
    json_float(data)       -> Float or Error     any finite number
    json_bool(data)        -> Bool or Error      true or false
    json_length(data)      -> Int or Error       elements of an array, members
                                                  of an object
    json_keys(data)        -> List<String> or Error   member names in order
    json_items(data)       -> List<Data> or Error     array elements in order

Every call is pure and needs no capability. A missing member or index is
``KS3710``; a value of the wrong kind is ``KS3709``. Both are Error values the
caller handles with ``or``. Nothing is converted silently: ``json_int`` refuses
``2.5`` and numbers outside signed 64 bits, and ``json_float`` refuses numbers
that are not finite as a Float.

The builtins exist under ``ks run`` (checked-AST interpreter, canonical MIR
executor, direct MIR runtime). Native builds refuse ``Data`` programs with
``KS4004``, as they already do for ``parse_json``.
"""

from __future__ import annotations

import math
from typing import Any

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from .ast_nodes import CallExpression, Identifier
from .data_json_v1 import Number
from .data_language_v1 import DataValue
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .type_system import BOOL, ERROR, FLOAT, INT, STRING, NamedType, generic, union_type

DATA = NamedType("Data")
INT_MIN = -(1 << 63)
INT_MAX = (1 << 63) - 1

# name -> (parameter types as text, result type as text, parameter TypeNodes, result TypeNode)
SIGNATURES: dict[str, tuple[tuple[str, ...], str, tuple[Any, ...], Any]] = {
    "json_kind": (("Data",), "String", (DATA,), STRING),
    "json_has": (("Data", "String"), "Bool", (DATA, STRING), BOOL),
    "json_get": (("Data", "String"), "Data or Error", (DATA, STRING), union_type(DATA, ERROR)),
    "json_at": (("Data", "Int"), "Data or Error", (DATA, INT), union_type(DATA, ERROR)),
    "json_text": (("Data",), "String or Error", (DATA,), union_type(STRING, ERROR)),
    "json_int": (("Data",), "Int or Error", (DATA,), union_type(INT, ERROR)),
    "json_float": (("Data",), "Float or Error", (DATA,), union_type(FLOAT, ERROR)),
    "json_bool": (("Data",), "Bool or Error", (DATA,), union_type(BOOL, ERROR)),
    "json_length": (("Data",), "Int or Error", (DATA,), union_type(INT, ERROR)),
    "json_keys": (("Data",), "List<String> or Error", (DATA,), union_type(generic("List", STRING), ERROR)),
    "json_items": (("Data",), "List<Data> or Error", (DATA,), union_type(generic("List", DATA), ERROR)),
}
NAMES = frozenset(SIGNATURES)
FALLIBLE = frozenset(name for name, signature in SIGNATURES.items() if signature[1].endswith(" or Error"))

_INSTALLED = False
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_SEMANTIC_RECEIVER = None
_ORIGINAL_TYPED_CALL_TYPE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_MIR_INVOKE = None


class _Failure(Exception):
    """An Error value to hand back to the program."""


def kind_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Number):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise _Failure("KS3709: value is not JSON data")


def _data(name: str, value: Any) -> Any:
    if not isinstance(value, DataValue):
        raise _Failure(f"KS3709: {name}() expects Data")
    return value.value


def _expect(name: str, value: Any, wanted: str) -> Any:
    found = kind_of(value)
    if found != wanted:
        raise _Failure(f"KS3709: {name}() expects a JSON {wanted}, found {found}")
    return value


def access(name: str, arguments: list[Any] | tuple[Any, ...]) -> Any:
    """Evaluate one builtin. Lists come back as Python lists of host values.

    Raises ``_Failure`` with the Error message for the program.
    """
    value = _data(name, arguments[0])
    if name == "json_kind":
        return kind_of(value)
    if name == "json_has":
        key = arguments[1]
        return isinstance(value, dict) and isinstance(key, str) and key in value
    if name == "json_get":
        key = arguments[1]
        if not isinstance(key, str):
            raise _Failure("KS3709: json_get() expects a String key")
        _expect(name, value, "object")
        if key not in value:
            raise _Failure(f'KS3710: json_get(): no member named "{key}"')
        return DataValue(value[key])
    if name == "json_at":
        index = arguments[1]
        if isinstance(index, bool) or not isinstance(index, int):
            raise _Failure("KS3709: json_at() expects an Int index")
        _expect(name, value, "array")
        if not value:
            raise _Failure(f"KS3710: json_at(): index {index} in an empty array")
        if not 0 <= index < len(value):
            raise _Failure(f"KS3710: json_at(): index {index} is outside 0..{len(value) - 1}")
        return DataValue(value[index])
    if name == "json_text":
        return _expect(name, value, "string")
    if name == "json_bool":
        return _expect(name, value, "bool")
    if name == "json_int":
        text = _expect(name, value, "number").text
        if "." in text:
            raise _Failure(f"KS3709: json_int(): {text} is not an integer")
        number = int(text)
        if not INT_MIN <= number <= INT_MAX:
            raise _Failure(f"KS3709: json_int(): {text} is outside the Int range")
        return number
    if name == "json_float":
        text = _expect(name, value, "number").text
        try:
            number = float(text)
        except (OverflowError, ValueError):
            number = math.inf
        if not math.isfinite(number):
            raise _Failure(f"KS3709: json_float(): {text} is outside the Float range")
        return number
    if name == "json_length":
        if isinstance(value, (list, dict)):
            return len(value)
        raise _Failure(f"KS3709: json_length() expects a JSON array or object, found {kind_of(value)}")
    if name == "json_keys":
        return list(_expect(name, value, "object"))
    if name == "json_items":
        return [DataValue(item) for item in _expect(name, value, "array")]
    raise AssertionError(name)


def _is_access_call(expression) -> bool:
    return (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in NAMES
    )


def _semantic_expression(self, expression):
    if _is_access_call(expression):
        name = expression.callee.name
        parameters, result, _, _ = SIGNATURES[name]
        if len(expression.arguments) != len(parameters):
            raise _semantic.SemanticError(
                "KS1301",
                f"'{name}' {len(parameters)} argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        for position, (argument, expected) in enumerate(zip(expression.arguments, parameters), start=1):
            actual = self._check_expression(argument)
            self._require_assignable((expected,), actual, f"'{name}' {position}. argümanı", expression.location)
        return result
    return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)


def _semantic_fallible(self, expression):
    if _is_access_call(expression):
        return expression.callee.name in FALLIBLE
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _semantic_receiver(self, expression):
    if _is_access_call(expression):
        return SIGNATURES[expression.callee.name][1]
    return _ORIGINAL_SEMANTIC_RECEIVER(self, expression)


def _typed_call_type(self, name, arguments, location):
    if name not in NAMES:
        return _ORIGINAL_TYPED_CALL_TYPE(self, name, arguments, location)
    _, _, parameters, result = SIGNATURES[name]
    if len(arguments) != len(parameters):
        raise _semantic.SemanticError(
            "KS1301",
            f"'{name}' {len(parameters)} argüman bekler, {len(arguments)} verildi.",
            location,
        )
    for position, (actual, expected) in enumerate(zip(arguments, parameters), start=1):
        _contracts.require_assignable(expected, actual, f"'{name}' {position}. argümanı", location)
    return result


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in NAMES:
        return expression.name
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if isinstance(callee, str) and callee in NAMES:
        self._require_arity(callee, arguments, len(SIGNATURES[callee][0]), location)
        try:
            return access(callee, arguments)
        except _Failure as failure:
            return _runtime.KsError(str(failure))
    return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)


def _mir_invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name in NAMES:
        name = callee.name
        if len(arguments) != len(SIGNATURES[name][0]):
            raise _mir.MirNativeRuntimeError(f"{name} expects {len(SIGNATURES[name][0])} argument(s)")
        try:
            result = access(name, arguments)
        except _Failure as failure:
            return _mir._ErrorValue(str(failure))
        # The direct MIR runtime represents List values as tuples.
        return tuple(result) if isinstance(result, list) else result
    return _ORIGINAL_MIR_INVOKE(self, callee, arguments)


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    example = 'let name = json_text(json_get(data, "name") or return Error("no name")) or "unknown"'
    entries = {
        "KS3709": (
            ("JSON değeri beklenen türde değil", "Bir Data değeri, istenen türden farklı bir JSON türü taşıyor.",
             "json_text bir JSON metni, json_int tam sayı olan bir JSON sayısı, json_get bir JSON nesnesi ister. Sessiz dönüşüm yapılmaz.",
             "json_kind(data) ile türe bakın ya da hatayı 'or' ile ele alın."),
            ("JSON value has a different kind", "A Data value holds a different JSON kind from the one requested.",
             "json_text needs a JSON string, json_int a JSON number that is an integer, json_get a JSON object. Nothing is converted silently.",
             "Check the kind with json_kind(data), or handle the Error with 'or'."),
        ),
        "KS3710": (
            ("JSON üyesi veya dizin yok", "İstenen nesne üyesi ya da dizi dizini Data değerinde yok.",
             "json_get var olmayan bir üyeyi, json_at dizinin dışındaki bir dizini istedi.",
             "Önce json_has(data, key) veya json_length(data) ile denetleyin ya da hatayı 'or' ile ele alın."),
            ("JSON member or index not found", "The requested object member or array index is not in the Data value.",
             "json_get asked for a member that is absent, or json_at for an index outside the array.",
             "Check first with json_has(data, key) or json_length(data), or handle the Error with 'or'."),
        ),
    }
    for code, (tr, en) in entries.items():
        CATALOG[code] = Diagnostic(code, tr[0], tr[1], tr[2], tr[3], example)
        ENGLISH_CATALOG[code] = Diagnostic(code, en[0], en[1], en[2], en[3], example)


def install_data_access_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_SEMANTIC_EXPRESSION, _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_SEMANTIC_RECEIVER, _ORIGINAL_TYPED_CALL_TYPE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE, _ORIGINAL_MIR_INVOKE
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(NAMES)
    # Reading a value is deterministic: allowed inside `pure fn`.
    _effects._PURE_BUILTINS.update(NAMES)
    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINAL_SEMANTIC_RECEIVER = _semantic.SemanticChecker._receiver_type
    _semantic.SemanticChecker._receiver_type = _semantic_receiver

    _ORIGINAL_TYPED_CALL_TYPE = _typed_hir.TypedHIRChecker.call_type
    _typed_hir.TypedHIRChecker.call_type = _typed_call_type

    # Checked-AST interpreter; the canonical MIR executor reaches it through
    # the runtime primitive facade's builtin allowlist.
    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke
    # parse_json and encode_json were never on this allowlist, so any program
    # that imported a module (and so ran on the canonical MIR executor) failed
    # with KS3101 at its first parse_json call. Add them with the readers.
    RuntimePrimitiveFacadeV1._BUILTIN_CALLS = frozenset(
        RuntimePrimitiveFacadeV1._BUILTIN_CALLS | NAMES | {"parse_json", "encode_json"}
    )

    # Direct MIR runtime.
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | NAMES)
    _ORIGINAL_MIR_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke

    _register_diagnostics()
    _INSTALLED = True


__all__ = ["NAMES", "SIGNATURES", "access", "install_data_access_v1", "kind_of"]
