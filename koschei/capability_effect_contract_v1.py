"""Canonical capability contract for Koschei.

This module is the single source of truth for capability shape and capability
method effect names. Typed HIR helpers, source-level effect checking and MIR
sealing consume this contract rather than maintaining parallel taxonomies.

The legacy semantic checker still exposes compatibility aliases during the
migration. Tests require those aliases to remain byte-for-byte equivalent to
this contract until semantic.py is reduced to a consumer.
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


def narrowed_type_for(root_type: str, method: str) -> str | None:
    """Return the authority type produced by one legal narrowing operation."""

    return ROOT_NARROWING.get(root_type, {}).get(method)


def operation_allowed(capability_type: str, method: str) -> bool:
    """Return whether a narrowed capability admits the operation."""

    return method in NARROWED_OPERATIONS.get(capability_type, frozenset())


def effect_for(capability_type: str, method: str) -> str | None:
    """Return the canonical effect for one capability method, if defined."""

    return CAPABILITY_METHOD_EFFECTS.get(capability_type, {}).get(method)
