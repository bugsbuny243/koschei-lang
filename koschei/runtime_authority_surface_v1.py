"""Canonical runtime authority-surface helpers for Koschei.

The interpreter owns implementation code, but it must not own a second copy of
which capability members are language-visible or how capability runtime values
map back to canonical capability type names.  This module derives both views
from the canonical capability contract and runtime capability registry.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from .capability_effect_contract_v1 import (
    NARROWED_OPERATIONS,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)
from .runtime_capability_registry_v1 import runtime_capability_types


def capability_members_for_type(type_name: str) -> frozenset[str]:
    """Return the language-visible members for one capability type."""

    if type_name == "SystemCaps":
        return frozenset(SYSTEM_CAPABILITY_MEMBERS)
    if type_name in ROOT_NARROWING:
        return frozenset(ROOT_NARROWING[type_name])
    return frozenset(NARROWED_OPERATIONS.get(type_name, frozenset()))


def runtime_capability_type_name(runtime: ModuleType, value: Any) -> str | None:
    """Resolve a runtime capability value to its canonical Koschei type name."""

    for type_name, runtime_type in runtime_capability_types(runtime).items():
        if isinstance(value, runtime_type):
            return type_name
    return None


def runtime_value_matches_capability(
    runtime: ModuleType,
    value: Any,
    expected_type_name: str,
) -> bool:
    """Match a value against one canonical capability type without hard-coded ladders."""

    runtime_type = runtime_capability_types(runtime).get(expected_type_name)
    return runtime_type is not None and isinstance(value, runtime_type)


def capability_member_allowed(
    runtime: ModuleType,
    value: Any,
    member: str,
) -> bool:
    """Return whether a runtime capability value exposes a canonical member."""

    type_name = runtime_capability_type_name(runtime, value)
    if type_name is None:
        return False
    return member in capability_members_for_type(type_name)
