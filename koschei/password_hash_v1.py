"""Message authentication and password hashing (``password_hash_v1``).

    let tag = hmac_sha256(key, body)                       // lowercase hex
    let hash = pbkdf2_sha256(password, salt, 600000, 32) or return
    if secure_equal(tag, sent) { ... }                    // constant time

Koschei implements no cryptographic primitive: HMAC-SHA256 and PBKDF2-HMAC-
SHA256 come from Python's ``hmac``/``hashlib`` under ``ks run`` and from Go's
``crypto/hmac``, ``crypto/sha256`` and ``crypto/pbkdf2`` in native binaries,
and ``secure_equal`` from ``hmac.compare_digest`` / ``crypto/subtle``. The
parameters PBKDF2 accepts are bounded so a stored hash is never weak by
accident: a salt of 16 to 1024 bytes, 100,000 to 10,000,000 iterations and a
key of 16 to 64 bytes. A parameter outside them is a ``KS3490`` Error value.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from .ast_nodes import CallExpression, Identifier
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .type_system import BOOL, ERROR, INT, STRING, NamedType, union_type

_BYTES = NamedType("Bytes")

MIN_SALT_BYTES, MAX_SALT_BYTES = 16, 1024
MIN_ITERATIONS, MAX_ITERATIONS = 100_000, 10_000_000
MIN_KEY_BYTES, MAX_KEY_BYTES = 16, 64
MAX_PASSWORD_BYTES = 4096

SALT_MESSAGE = f"KS3490: pbkdf2_sha256 salt must be {MIN_SALT_BYTES}..{MAX_SALT_BYTES} bytes"
ITERATIONS_MESSAGE = f"KS3490: pbkdf2_sha256 iterations must be {MIN_ITERATIONS}..{MAX_ITERATIONS}"
KEY_MESSAGE = f"KS3490: pbkdf2_sha256 key length must be {MIN_KEY_BYTES}..{MAX_KEY_BYTES} bytes"
PASSWORD_MESSAGE = f"KS3490: pbkdf2_sha256 password must be at most {MAX_PASSWORD_BYTES} bytes"

# name: (legacy argument types, typed argument types, legacy result, typed result)
SIGNATURES = {
    "hmac_sha256": (("Bytes", "Bytes"), (_BYTES, _BYTES), "String", STRING),
    "pbkdf2_sha256": (
        ("Bytes", "Bytes", "Int", "Int"), (_BYTES, _BYTES, INT, INT), "String or Error", union_type(STRING, ERROR),
    ),
    "secure_equal": (("String", "String"), (STRING, STRING), "Bool", BOOL),
}
BUILTINS = frozenset(SIGNATURES)
_FALLIBLE = frozenset(name for name, signature in SIGNATURES.items() if signature[2].endswith("or Error"))

_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


# ---- the operations, shared by every Python executor -----------------------


def hmac_sha256(key: "_runtime.Bytes", message: "_runtime.Bytes") -> str:
    return hmac.new(bytes(key), bytes(message), hashlib.sha256).hexdigest()


def pbkdf2_sha256(password: "_runtime.Bytes", salt: "_runtime.Bytes", iterations: int, length: int) -> Any:
    # The order of the checks is part of the contract: native binaries share it.
    if not MIN_SALT_BYTES <= len(salt) <= MAX_SALT_BYTES:
        return _runtime.KsError(SALT_MESSAGE)
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        return _runtime.KsError(ITERATIONS_MESSAGE)
    if not MIN_KEY_BYTES <= length <= MAX_KEY_BYTES:
        return _runtime.KsError(KEY_MESSAGE)
    if len(password) > MAX_PASSWORD_BYTES:
        return _runtime.KsError(PASSWORD_MESSAGE)
    return hashlib.pbkdf2_hmac("sha256", bytes(password), bytes(salt), iterations, length).hex()


def secure_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


_OPERATIONS = {"hmac_sha256": hmac_sha256, "pbkdf2_sha256": pbkdf2_sha256, "secure_equal": secure_equal}


def call(name: str, arguments: list[Any]) -> Any:
    for argument, expected in zip(arguments, SIGNATURES[name][0]):
        kind = _runtime.Bytes if expected == "Bytes" else (str if expected == "String" else int)
        if not isinstance(argument, kind) or isinstance(argument, bool):
            raise _runtime.KoscheiRuntimeError("KS3101", f"'{name}' argümanı {expected} değil.")
    return _OPERATIONS[name](*arguments)


# ---- checkers ---------------------------------------------------------------


def _called(expression) -> str | None:
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in BUILTINS
    ):
        return expression.callee.name
    return None


def _arity(name: str, count: int, location) -> None:
    expected = len(SIGNATURES[name][0])
    if count != expected:
        raise _semantic.SemanticError(
            "KS1301", f"'{name}' {expected} argüman bekler, {count} verildi.", location
        )


def _semantic_expression(self, expression):
    name = _called(expression)
    if name is None:
        return _ORIGINALS["semantic_expression"](self, expression)
    _arity(name, len(expression.arguments), expression.location)
    for index, (wanted, argument) in enumerate(zip(SIGNATURES[name][0], expression.arguments), start=1):
        actual = self._check_expression(argument)
        self._require_assignable((wanted,), actual, f"'{name}' çağrısının {index}. argümanı", expression.location)
    return SIGNATURES[name][2]


def _semantic_fallible(self, expression):
    if _called(expression) in _FALLIBLE:
        return True
    return _ORIGINALS["semantic_fallible"](self, expression)


def _semantic_receiver(self, expression):
    name = _called(expression)
    if name is not None:
        return SIGNATURES[name][2]
    return _ORIGINALS["semantic_receiver"](self, expression)


def _typed_call_type(self, name, arguments, location):
    if name not in BUILTINS:
        return _ORIGINALS["typed_call_type"](self, name, arguments, location)
    _arity(name, len(arguments), location)
    for index, (wanted, actual) in enumerate(zip(SIGNATURES[name][1], arguments), start=1):
        _contracts.require_assignable(wanted, actual, f"'{name}' çağrısının {index}. argümanı", location)
    return SIGNATURES[name][3]


# ---- runtimes ---------------------------------------------------------------


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in BUILTINS:
        return expression.name
    return _ORIGINALS["runtime_evaluate"](self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if isinstance(callee, str) and callee in BUILTINS:
        self._require_arity(callee, arguments, len(SIGNATURES[callee][0]), location)
        return call(callee, arguments)
    return _ORIGINALS["runtime_invoke"](self, callee, arguments, location)


def _mir_invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name in BUILTINS:
        if len(arguments) != len(SIGNATURES[callee.name][0]):
            raise _mir.MirNativeRuntimeError(f"{callee.name} expects {len(SIGNATURES[callee.name][0])} arguments")
        result = call(callee.name, arguments)
        if isinstance(result, _runtime.KsError):
            return _mir._ErrorValue(result.message)
        return result
    return _ORIGINALS["mir_invoke"](self, callee, arguments)


def install_password_hash_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(BUILTINS)
    _effects._PURE_BUILTINS.update(BUILTINS)

    _ORIGINALS["semantic_expression"] = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINALS["semantic_fallible"] = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINALS["semantic_receiver"] = _semantic.SemanticChecker._receiver_type
    _semantic.SemanticChecker._receiver_type = _semantic_receiver
    _ORIGINALS["typed_call_type"] = _typed_hir.TypedHIRChecker.call_type
    _typed_hir.TypedHIRChecker.call_type = _typed_call_type

    _ORIGINALS["runtime_evaluate"] = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINALS["runtime_invoke"] = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke

    RuntimePrimitiveFacadeV1._BUILTIN_CALLS = frozenset(RuntimePrimitiveFacadeV1._BUILTIN_CALLS | BUILTINS)

    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | BUILTINS)
    _ORIGINALS["mir_invoke"] = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke
    _INSTALLED = True


__all__ = [
    "BUILTINS",
    "ITERATIONS_MESSAGE",
    "KEY_MESSAGE",
    "PASSWORD_MESSAGE",
    "SALT_MESSAGE",
    "SIGNATURES",
    "hmac_sha256",
    "install_password_hash_v1",
    "pbkdf2_sha256",
    "secure_equal",
]
