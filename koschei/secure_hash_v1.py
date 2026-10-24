"""Kernel SHA3-256 digest for the Koschei Core Library.

Koschei does not implement cryptographic primitives (``crypto_agility_v1``).
``sha3_256(text)`` delegates to the host's audited standard implementation —
Python ``hashlib`` here and Go ``crypto/sha3`` in MIR-Go binaries — and returns
the digest of the String's UTF-8 bytes as 64 lowercase hex characters.

The input is bounded: more than ``SHA3_256_MAX_INPUT_BYTES`` bytes produces an
Error value instead of a digest, which also bounds the work of one call. The
call is pure: it needs no capability and carries none.

The builtin is a kernel primitive. Programs use it through the Koschei-written
``secure`` Core Library module (``secure.hash``, ``secure.digest``).
"""

from __future__ import annotations

import hashlib

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from .ast_nodes import CallExpression, Identifier
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .type_system import ERROR, STRING, union_type

NAME = "sha3_256"
SHA3_256_MAX_INPUT_BYTES = 1 << 20

_INSTALLED = False
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_SEMANTIC_RECEIVER = None
_ORIGINAL_TYPED_CALL_TYPE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_MIR_INVOKE = None


def sha3_256_hex(value: object) -> tuple[str | None, str | None]:
    """Return ``(digest, None)`` or ``(None, error message)``."""

    if not isinstance(value, str):
        return None, f"{NAME}: input must be a String"
    data = value.encode("utf-8")
    if len(data) > SHA3_256_MAX_INPUT_BYTES:
        return None, f"{NAME}: input exceeds {SHA3_256_MAX_INPUT_BYTES} bytes"
    return hashlib.sha3_256(data).hexdigest(), None


def _is_digest_call(expression) -> bool:
    return (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name == NAME
    )


def _semantic_expression(self, expression):
    if _is_digest_call(expression):
        if len(expression.arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301",
                f"'{NAME}' 1 argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        actual = self._check_expression(expression.arguments[0])
        self._require_assignable(
            ("String",), actual, f"'{NAME}' argümanı", expression.location
        )
        return "String or Error"
    return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)


def _semantic_fallible(self, expression):
    if _is_digest_call(expression):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _semantic_receiver(self, expression):
    if _is_digest_call(expression):
        return "String or Error"
    return _ORIGINAL_SEMANTIC_RECEIVER(self, expression)


def _typed_call_type(self, name, arguments, location):
    if name != NAME:
        return _ORIGINAL_TYPED_CALL_TYPE(self, name, arguments, location)
    if len(arguments) != 1:
        raise _semantic.SemanticError(
            "KS1301",
            f"'{NAME}' 1 argüman bekler, {len(arguments)} verildi.",
            location,
        )
    _contracts.require_assignable(STRING, arguments[0], f"'{NAME}' argümanı", location)
    return union_type(STRING, ERROR)


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name == NAME:
        return NAME
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if callee == NAME:
        self._require_arity(NAME, arguments, 1, location)
        digest, error = sha3_256_hex(arguments[0])
        return _runtime.KsError(error) if error is not None else digest
    return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)


def _mir_invoke(self, callee, arguments):
    if isinstance(callee, _mir._BuiltinRef) and callee.name == NAME:
        if len(arguments) != 1:
            raise _mir.MirNativeRuntimeError(f"{NAME} expects one argument")
        digest, error = sha3_256_hex(arguments[0])
        return _mir._ErrorValue(error) if error is not None else digest
    return _ORIGINAL_MIR_INVOKE(self, callee, arguments)


def install_secure_hash_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_SEMANTIC_EXPRESSION, _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_SEMANTIC_RECEIVER, _ORIGINAL_TYPED_CALL_TYPE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE, _ORIGINAL_MIR_INVOKE
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.add(NAME)
    # A digest is a deterministic value: allowed inside `pure fn`.
    _effects._PURE_BUILTINS.add(NAME)
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
    RuntimePrimitiveFacadeV1._BUILTIN_CALLS = frozenset(
        RuntimePrimitiveFacadeV1._BUILTIN_CALLS | {NAME}
    )

    # Direct MIR runtime.
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | {NAME})
    _ORIGINAL_MIR_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke
    _INSTALLED = True


__all__ = ["NAME", "SHA3_256_MAX_INPUT_BYTES", "install_secure_hash_v1", "sha3_256_hex"]
