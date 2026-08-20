"""Canonical capability contract for Koschei.

This module is the single source of truth for capability shape, capability
method effect names, and capability-boundary policy constants. Typed HIR
helpers, source-level effect checking and MIR sealing consume this contract
rather than maintaining parallel taxonomies.

The legacy semantic checker and tree-walking runtime still expose compatibility
constants during the migration. Alignment tests require those views to remain
equivalent to this contract until they are reduced to direct consumers.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

AUTHORITY_DERIVE = "authority.derive"
NET_IO = "net.io"
DISK_READ = "disk.read"
DISK_WRITE = "disk.write"
ENV_READ = "env.read"
PROCESS_EXEC = "process.exec"

# Network authority may only be narrowed to explicit HTTP(S) origins. This is a
# language-level authority rule, not a parser/runtime implementation detail.
NET_ORIGIN_SCHEMES = frozenset({"http", "https"})

_SYSTEM_CAPABILITY_MEMBERS = {
    "net": "NetRoot",
    "disk": "DiskRoot",
    "env": "EnvRoot",
    "process": "ProcessRoot",
}

_ROOT_NARROWING = {
    "NetRoot": {"allow": "NetCaps"},
    "DiskRoot": {"allow": "DiskCaps", "allow_read_only": "DiskReadCaps"},
    "EnvRoot": {"allow": "EnvCaps"},
    "ProcessRoot": {"allow": "ProcessCaps"},
}

_NARROWED_OPERATIONS = {
    "NetCaps": {"get", "post", "put", "delete", "request"},
    "DiskCaps": {"read", "write", "delete", "list", "read_file", "write_file"},
    "DiskReadCaps": {"read", "list", "read_file"},
    "EnvCaps": {"get"},
    "ProcessCaps": {"run", "spawn"},
}

_CAPABILITY_METHOD_EFFECTS = {
    "NetRoot": {"allow": AUTHORITY_DERIVE},
    "DiskRoot": {
        "allow": AUTHORITY_DERIVE,
        "allow_read_only": AUTHORITY_DERIVE,
    },
    "EnvRoot": {"allow": AUTHORITY_DERIVE},
    "ProcessRoot": {"allow": AUTHORITY_DERIVE},
    "NetCaps": {
        "get": NET_IO,
        "post": NET_IO,
        "put": NET_IO,
        "delete": NET_IO,
        "request": NET_IO,
    },
    "DiskReadCaps": {
        "read": DISK_READ,
        "read_file": DISK_READ,
        "list": DISK_READ,
    },
    "DiskCaps": {
        "read": DISK_READ,
        "read_file": DISK_READ,
        "list": DISK_READ,
        "write": DISK_WRITE,
        "write_file": DISK_WRITE,
        "delete": DISK_WRITE,
    },
    "EnvCaps": {"get": ENV_READ},
    "ProcessCaps": {"run": PROCESS_EXEC, "spawn": PROCESS_EXEC},
}

SYSTEM_CAPABILITY_MEMBERS: Mapping[str, str] = MappingProxyType(
    dict(_SYSTEM_CAPABILITY_MEMBERS)
)
ROOT_NARROWING: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        capability: MappingProxyType(dict(methods))
        for capability, methods in _ROOT_NARROWING.items()
    }
)
NARROWED_OPERATIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        capability: frozenset(methods)
        for capability, methods in _NARROWED_OPERATIONS.items()
    }
)
CAPABILITY_METHOD_EFFECTS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        capability: MappingProxyType(dict(methods))
        for capability, methods in _CAPABILITY_METHOD_EFFECTS.items()
    }
)

NARROWING_METHODS = frozenset(
    method for methods in ROOT_NARROWING.values() for method in methods
)
GUARDED_METHODS = frozenset(
    method for methods in NARROWED_OPERATIONS.values() for method in methods
)
ROOT_CAPABILITY_TYPES = frozenset(ROOT_NARROWING) | {"SystemCaps"}
CAPABILITY_TYPES = ROOT_CAPABILITY_TYPES | frozenset(NARROWED_OPERATIONS)
CANONICAL_CAPABILITY_EFFECTS = frozenset(
    effect
    for methods in CAPABILITY_METHOD_EFFECTS.values()
    for effect in methods.values()
)


def legacy_semantic_members() -> dict[str, str]:
    """Return semantic.py's historical mutable member-table shape.

    This adapter exists only for migration. Consumers receive a fresh container,
    while all authority facts remain sourced from this canonical module.
    """

    return dict(SYSTEM_CAPABILITY_MEMBERS)


def legacy_semantic_root_methods() -> dict[str, dict[str, str]]:
    """Return semantic.py's historical mutable root-method table shape."""

    return {
        capability: dict(methods)
        for capability, methods in ROOT_NARROWING.items()
    }


def legacy_semantic_narrowed_methods() -> dict[str, set[str]]:
    """Return semantic.py's historical mutable narrowed-operation shape."""

    return {
        capability: set(methods)
        for capability, methods in NARROWED_OPERATIONS.items()
    }


def narrowed_type_for(root_type: str, method: str) -> str | None:
    """Return the authority type produced by one legal narrowing operation."""

    return ROOT_NARROWING.get(root_type, {}).get(method)


def operation_allowed(capability_type: str, method: str) -> bool:
    """Return whether a narrowed capability admits the operation."""

    return method in NARROWED_OPERATIONS.get(capability_type, frozenset())


def effect_for(capability_type: str, method: str) -> str | None:
    """Return the canonical effect for one capability method, if defined."""

    return CAPABILITY_METHOD_EFFECTS.get(capability_type, {}).get(method)
