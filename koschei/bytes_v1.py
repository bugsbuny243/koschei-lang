"""The ``Bytes`` type v1 (readiness gate G1.3).

``Bytes`` is an immutable byte sequence, distinct from ``String`` (which is
always valid UTF-8 text). It is a value: ``+`` concatenates, ``==``/``<``
compare byte by byte, and it renders as ``Bytes(68656c6c6f)``.

    let data = "héllo".to_bytes()          // UTF-8 encoding, never fails
    data.length()                          // 6
    data.hex()                             // "68c3a96c6c6f"
    data.get(1) or -1                      // 195
    data.slice(0, 2) or data               // Bytes(68c3)
    data.to_text() or "?"                  // "héllo"; KS3430 when not UTF-8
    bytes_from_hex("00ff") or data         // KS3461 when not even-length hex
    sha3_256_bytes(data) or "?"            // digest of the bytes themselves

Sources of binary data: ``InputCaps.read_bytes()`` and
``RandomCaps.bytes(count)``. A ``Bytes`` value holds at most 16 MiB
(``KS3502``), the same budget as a String.
"""

from __future__ import annotations

import hashlib
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
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .secure_hash_v1 import SHA3_256_MAX_INPUT_BYTES
from .type_system import ERROR, INT, STRING, NamedType, union_type

BYTES = NamedType("Bytes")
FROM_HEX = "bytes_from_hex"
SHA3_BYTES = "sha3_256_bytes"
BUILTINS = (FROM_HEX, SHA3_BYTES)
METHODS = {
    # name: (argument count, legacy result type)
    "length": (0, "Int"),
    "hex": (0, "String"),
    "to_text": (0, "String or Error"),
    "slice": (2, "Bytes or Error"),
    "get": (1, "Int or Error"),
}
_TYPED_METHODS = {
    "length": INT,
    "hex": STRING,
    "to_text": union_type(STRING, ERROR),
    "slice": union_type(BYTES, ERROR),
    "get": union_type(INT, ERROR),
}

NOT_TEXT_MESSAGE = "KS3430: Bytes geçerli UTF-8 metin değil."
SLICE_MESSAGE = "KS3460: Bytes.slice() aralığı geçersiz: {start}..{end} (uzunluk {length})."
GET_MESSAGE = "KS3460: Bytes.get() indeksi aralık dışında: {index} (uzunluk {length})."
HEX_MESSAGE = "KS3461: bytes_from_hex() çift uzunlukta bir hex metni bekler."
SHA3_TYPE_MESSAGE = f"{SHA3_BYTES}: input must be Bytes"
SHA3_SIZE_MESSAGE = f"{SHA3_BYTES}: input exceeds {SHA3_256_MAX_INPUT_BYTES} bytes"

_HEX = re.compile(r"(?:[0-9a-fA-F]{2})*")

_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


# ---- the operations, shared by every Python executor -----------------------


def bytes_method(receiver: "_runtime.Bytes", name: str, arguments: list[Any]) -> Any:
    if name == "length":
        return len(receiver)
    if name == "hex":
        return receiver.hex()
    if name == "to_text":
        try:
            return bytes(receiver).decode("utf-8")
        except UnicodeDecodeError:
            return _runtime.KsError(NOT_TEXT_MESSAGE)
    if name == "slice":
        start, end = arguments
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(receiver):
            return _runtime.KsError(
                SLICE_MESSAGE.format(start=start, end=end, length=len(receiver))
            )
        return _runtime.Bytes(receiver[start:end])
    if name == "get":
        (index,) = arguments
        if type(index) is not int or not 0 <= index < len(receiver):
            return _runtime.KsError(GET_MESSAGE.format(index=index, length=len(receiver)))
        return receiver[index]
    raise AssertionError(name)


def from_hex(value: Any) -> Any:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        return _runtime.KsError(HEX_MESSAGE)
    return _runtime.Bytes(bytes.fromhex(value))


def sha3_bytes(value: Any) -> Any:
    if not isinstance(value, _runtime.Bytes):
        return _runtime.KsError(SHA3_TYPE_MESSAGE)
    if len(value) > SHA3_256_MAX_INPUT_BYTES:
        return _runtime.KsError(SHA3_SIZE_MESSAGE)
    return hashlib.sha3_256(bytes(value)).hexdigest()


def _builtin(name: str, arguments: list[Any]) -> Any:
    (argument,) = arguments
    return from_hex(argument) if name == FROM_HEX else sha3_bytes(argument)


# ---- legacy checker ---------------------------------------------------------


def _is_builtin_call(expression) -> str | None:
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in BUILTINS
    ):
        return expression.callee.name
    return None


def _semantic_expression(self, expression):
    name = _is_builtin_call(expression)
    if name is not None:
        if len(expression.arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301",
                f"'{name}' 1 argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        actual = self._check_expression(expression.arguments[0])
        expected = "String" if name == FROM_HEX else "Bytes"
        self._require_assignable((expected,), actual, f"'{name}' argümanı", expression.location)
        return "Bytes or Error" if name == FROM_HEX else "String or Error"
    return _ORIGINALS["semantic_expression"](self, expression)


def _semantic_fallible(self, expression):
    if _is_builtin_call(expression) is not None:
        return True
    callee = getattr(expression, "callee", None)
    if isinstance(expression, CallExpression) and hasattr(callee, "member"):
        if callee.member in {"to_text", "slice", "get"} and self._receiver_type(callee.object) == "Bytes":
            return True
    return _ORIGINALS["semantic_fallible"](self, expression)


def _semantic_receiver(self, expression):
    name = _is_builtin_call(expression)
    if name is not None:
        return "Bytes or Error" if name == FROM_HEX else "String or Error"
    return _ORIGINALS["semantic_receiver"](self, expression)


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    values = argument_types or []
    if receiver_type == "String" and method_name == "to_bytes":
        if values:
            raise _semantic.SemanticError(
                "KS1301", f"String.to_bytes() 0 argüman bekler, {len(values)} verildi.", location
            )
        return "Bytes"
    if receiver_type in {"DiskCaps", "DiskReadCaps"} and method_name == "read_bytes":
        if len(values) != 1:
            raise _semantic.SemanticError(
                "KS1301", f"{receiver_type}.read_bytes() 1 argüman bekler, {len(values)} verildi.", location
            )
        self._require_assignable(("String",), values[0], f"{receiver_type}.read_bytes() yolu", location)
        return "Bytes or Error"
    if receiver_type == "Bytes":
        operation = METHODS.get(method_name)
        if operation is None:
            raise _semantic.SemanticError(
                "KS1502",
                f"Bytes üzerinde '{method_name}' metodu yok. "
                f"Kullanılabilir: {', '.join(sorted(METHODS))}.",
                location,
            )
        expected, result = operation
        if len(values) != expected:
            raise _semantic.SemanticError(
                "KS1301",
                f"Bytes.{method_name}() {expected} argüman bekler, {len(values)} verildi.",
                location,
            )
        for value in values:
            self._require_assignable(("Int",), value, f"Bytes.{method_name}() argümanı", location)
        return result
    return _ORIGINALS["check_method_call"](self, receiver_type, method_name, location, argument_types, arguments)


# ---- Typed HIR --------------------------------------------------------------


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType):
        if receiver.name in {"DiskCaps", "DiskReadCaps"} and method == "read_bytes":
            if len(arguments) != 1:
                raise _semantic.SemanticError(
                    "KS1301", f"{receiver.name}.read_bytes() 1 argüman bekler, {len(arguments)} verildi.", location
                )
            _contracts.require_assignable(STRING, arguments[0], f"{receiver.name}.read_bytes() yolu", location)
            return union_type(BYTES, ERROR)
        if receiver.name == "String" and method == "to_bytes":
            if arguments:
                raise _semantic.SemanticError(
                    "KS1301", f"String.to_bytes() 0 argüman bekler, {len(arguments)} verildi.", location
                )
            return BYTES
        if receiver.name == "Bytes":
            operation = METHODS.get(method)
            if operation is None:
                raise _semantic.SemanticError(
                    "KS1306", f"'{method}' işlemi Bytes tipi için güvenli değildir.", location
                )
            if len(arguments) != operation[0]:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"Bytes.{method}() {operation[0]} argüman bekler, {len(arguments)} verildi.",
                    location,
                )
            for argument in arguments:
                _contracts.require_assignable(INT, argument, f"Bytes.{method}() argümanı", location)
            return _TYPED_METHODS[method]
    return _ORIGINALS["method_type"](receiver, method, arguments, location)


def _typed_call_type(self, name, arguments, location):
    if name not in BUILTINS:
        return _ORIGINALS["typed_call_type"](self, name, arguments, location)
    if len(arguments) != 1:
        raise _semantic.SemanticError(
            "KS1301", f"'{name}' 1 argüman bekler, {len(arguments)} verildi.", location
        )
    expected = STRING if name == FROM_HEX else BYTES
    _contracts.require_assignable(expected, arguments[0], f"'{name}' argümanı", location)
    return union_type(BYTES, ERROR) if name == FROM_HEX else union_type(STRING, ERROR)


# ---- runtimes ---------------------------------------------------------------


def _runtime_member(self, receiver, name, location):
    if isinstance(receiver, _runtime.Bytes) and name in METHODS:
        return _runtime._BoundMember(receiver, name, location)
    if isinstance(receiver, str) and name == "to_bytes":
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINALS["runtime_member"](self, receiver, name, location)


def _runtime_invoke_member(self, member, arguments):
    receiver = member.receiver
    if isinstance(receiver, _runtime.Bytes) and member.name in METHODS:
        self._require_arity(member.name, arguments, METHODS[member.name][0], member.location)
        return bytes_method(receiver, member.name, arguments)
    if isinstance(receiver, str) and member.name == "to_bytes":
        self._require_arity(member.name, arguments, 0, member.location)
        return _runtime.Bytes(receiver.encode("utf-8"))
    return _ORIGINALS["runtime_invoke_member"](self, member, arguments)


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in BUILTINS:
        return expression.name
    return _ORIGINALS["runtime_evaluate"](self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if callee in BUILTINS:
        self._require_arity(callee, arguments, 1, location)
        return _builtin(callee, arguments)
    return _ORIGINALS["runtime_invoke"](self, callee, arguments, location)


def _mir_invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name in BUILTINS:
        if len(arguments) != 1:
            raise _mir.MirNativeRuntimeError(f"{callee.name} expects one argument")
        result = _builtin(callee.name, arguments)
        if isinstance(result, _runtime.KsError):
            return _mir._ErrorValue(result.message)
        return result
    return _ORIGINALS["mir_invoke"](self, callee, arguments)


def _facade_member_allowed(cls, member):
    if isinstance(member.receiver, _runtime.Bytes):
        return member.name in METHODS
    if isinstance(member.receiver, str) and member.name == "to_bytes":
        return True
    return _ORIGINALS["facade_member_allowed"].__func__(cls, member)


def install_bytes_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(BUILTINS)
    _effects._PURE_BUILTINS.update(BUILTINS)
    _effects._PURE_VALUE_METHODS.update({"to_bytes", "hex", "to_text", "slice"})
    _contracts.RESERVED_TYPE_PARAMETERS.add("Bytes")

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

    _ORIGINALS["runtime_member"] = _runtime.Interpreter._member
    _runtime.Interpreter._member = _runtime_member
    _ORIGINALS["runtime_invoke_member"] = _runtime.Interpreter._invoke_member
    _runtime.Interpreter._invoke_member = _runtime_invoke_member
    _ORIGINALS["runtime_evaluate"] = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINALS["runtime_invoke"] = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke

    RuntimePrimitiveFacadeV1._BUILTIN_CALLS = frozenset(
        RuntimePrimitiveFacadeV1._BUILTIN_CALLS | set(BUILTINS)
    )
    _ORIGINALS["facade_member_allowed"] = RuntimePrimitiveFacadeV1.__dict__["_member_allowed"]
    RuntimePrimitiveFacadeV1._member_allowed = classmethod(_facade_member_allowed)

    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | set(BUILTINS))
    _ORIGINALS["mir_invoke"] = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke
    _INSTALLED = True


__all__ = [
    "BUILTINS",
    "FROM_HEX",
    "GET_MESSAGE",
    "HEX_MESSAGE",
    "METHODS",
    "NOT_TEXT_MESSAGE",
    "SHA3_BYTES",
    "SHA3_SIZE_MESSAGE",
    "SHA3_TYPE_MESSAGE",
    "SLICE_MESSAGE",
    "install_bytes_v1",
]
