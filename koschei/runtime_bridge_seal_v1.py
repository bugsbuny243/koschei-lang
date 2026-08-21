"""Deterministic integrity seal for the canonical interpreter authority bridge.

The bridge already rejects obvious replacement of its installed wrappers.  This
module adds an independent digest over the active wrapper code identities and the
canonical capability contract surface, then pins that digest on first validated
boot.  Later boots must reproduce the same digest or execution fails closed.
"""
from __future__ import annotations

import hashlib
from types import ModuleType
from typing import Any

from .capability_effect_contract_v1 import (
    CAPABILITY_TYPES,
    NARROWED_OPERATIONS,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)

_CTX = b"koschei.runtime-bridge-seal/v1\x00"
_SEAL_ATTR = "_canonical_authority_bridge_seal_v1"


class RuntimeBridgeSealError(RuntimeError):
    pass


def _code_identity(function: Any) -> bytes:
    code = getattr(function, "__code__", None)
    if code is None:
        raise RuntimeBridgeSealError("canonical bridge wrapper has no inspectable code")
    parts = (
        getattr(function, "__module__", ""),
        getattr(function, "__qualname__", ""),
        code.co_name,
        str(code.co_argcount),
        str(code.co_kwonlyargcount),
        code.co_code.hex(),
        repr(code.co_consts),
        repr(code.co_names),
    )
    return "\n".join(parts).encode("utf-8")


def runtime_bridge_fingerprint(runtime: ModuleType) -> str:
    interpreter_type = getattr(runtime, "Interpreter", None)
    if interpreter_type is None:
        raise RuntimeBridgeSealError("Interpreter runtime type is missing")
    if not getattr(interpreter_type, "_canonical_authority_bridge_v1", False):
        raise RuntimeBridgeSealError("canonical authority bridge is not installed")

    digest = hashlib.sha256()
    digest.update(_CTX)
    for name in ("_member", "_runtime_matches_type", "_runtime_type_name"):
        digest.update(name.encode("utf-8") + b"\x00")
        digest.update(_code_identity(getattr(interpreter_type, name)))

    for name in sorted(CAPABILITY_TYPES):
        digest.update(f"type={name}\n".encode("utf-8"))
    for member, type_name in sorted(SYSTEM_CAPABILITY_MEMBERS.items()):
        digest.update(f"system={member}:{type_name}\n".encode("utf-8"))
    for type_name, methods in sorted(ROOT_NARROWING.items()):
        digest.update(f"root={type_name}:{','.join(sorted(methods))}\n".encode("utf-8"))
    for type_name, methods in sorted(NARROWED_OPERATIONS.items()):
        digest.update(f"narrowed={type_name}:{','.join(sorted(methods))}\n".encode("utf-8"))
    return digest.hexdigest()


def require_runtime_bridge_sealed(runtime: ModuleType) -> str:
    """Pin the first valid bridge fingerprint and reject all later drift."""
    current = runtime_bridge_fingerprint(runtime)
    interpreter_type = runtime.Interpreter
    sealed = getattr(interpreter_type, _SEAL_ATTR, None)
    if sealed is None:
        setattr(interpreter_type, _SEAL_ATTR, current)
        return current
    if sealed != current:
        raise RuntimeBridgeSealError(
            "canonical runtime bridge fingerprint drifted after seal"
        )
    return current
