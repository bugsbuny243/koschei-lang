"""Canonical runtime bridge for the legacy tree-walking interpreter.

The interpreter still contains bootstrap-era capability tables. This bridge
replaces the active capability member/type decisions with canonical resolvers
without moving the implementation classes themselves. Implementation remains in
interpreter.py; language authority does not.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from .capability_effect_contract_v1 import CAPABILITY_TYPES, NARROWING_METHODS
from .runtime_authority_surface_v1 import (
    capability_member_allowed,
    runtime_capability_type_name,
    runtime_value_matches_capability,
)


class RuntimeAuthorityError(RuntimeError):
    """Raised when the runtime cannot be bound to canonical authority."""


def install_canonical_authority_bridge(runtime: ModuleType) -> None:
    """Make interpreter capability decisions consume canonical authority data.

    Installation is idempotent. Non-capability built-ins keep their existing
    implementation behavior. Capability type checks never fall back to the
    interpreter's bootstrap-era hard-coded ladder.
    """

    interpreter_type = getattr(runtime, "Interpreter", None)
    if interpreter_type is None:
        raise RuntimeAuthorityError("Interpreter runtime type is missing")
    if getattr(interpreter_type, "_canonical_authority_bridge_v1", False):
        return

    original_member = interpreter_type._member
    original_matches = interpreter_type._runtime_matches_type
    original_type_name = interpreter_type._runtime_type_name

    def canonical_member(self, receiver: Any, name: str, location: Any) -> Any:
        capability_type = runtime_capability_type_name(runtime, receiver)
        if capability_type == "SystemCaps":
            if capability_member_allowed(runtime, receiver, name):
                return getattr(receiver, name)
            raise runtime.KoscheiRuntimeError(
                "KS3404",
                f"SystemCaps canonical authority member '{name}' sağlamaz.",
                location,
            )
        if capability_type in CAPABILITY_TYPES:
            if name in NARROWING_METHODS and not capability_member_allowed(
                runtime, receiver, name
            ):
                raise runtime.KoscheiRuntimeError(
                    "KS3403",
                    f"Daraltılmış yetki '{name}' ile yeniden genişletilemez.",
                    location,
                )
            if not capability_member_allowed(runtime, receiver, name):
                raise runtime.KoscheiRuntimeError(
                    "KS3404",
                    f"{capability_type} '{name}' işlemine izin vermez.",
                    location,
                )
            return runtime._BoundMember(receiver, name, location)
        return original_member(self, receiver, name, location)

    def canonical_matches(self, value: Any, expected_names: Any) -> bool:
        expected = tuple(expected_names)
        capability_names = tuple(name for name in expected if name in CAPABILITY_TYPES)
        ordinary_names = tuple(name for name in expected if name not in CAPABILITY_TYPES)

        if any(
            runtime_value_matches_capability(runtime, value, name)
            for name in capability_names
        ):
            return True

        # Critical migration rule: canonical capability expectations are never
        # delegated back to the interpreter's legacy hard-coded capability ladder.
        # Only non-capability union members may use the old general type matcher.
        if ordinary_names:
            return original_matches(self, value, ordinary_names)
        return False

    def canonical_type_name(value: Any) -> str:
        capability_type = runtime_capability_type_name(runtime, value)
        if capability_type is not None:
            return capability_type
        return original_type_name(value)

    interpreter_type._member = canonical_member
    interpreter_type._runtime_matches_type = canonical_matches
    interpreter_type._runtime_type_name = staticmethod(canonical_type_name)
    interpreter_type._canonical_authority_bridge_v1 = True
