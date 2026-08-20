"""Canonical capability-to-effect contract for Koschei.

This module is the single source of truth for capability method effect names.
Source-level effect checking and MIR sealing must consume this contract rather
than maintaining parallel taxonomies. Capability typing/ownership/runtime
alignment can migrate onto the same contract in later slices.
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

CAPABILITY_METHOD_EFFECTS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        capability: MappingProxyType(dict(methods))
        for capability, methods in _CAPABILITY_METHOD_EFFECTS.items()
    }
)

CANONICAL_CAPABILITY_EFFECTS = frozenset(
    effect
    for methods in CAPABILITY_METHOD_EFFECTS.values()
    for effect in methods.values()
)


def effect_for(capability_type: str, method: str) -> str | None:
    """Return the canonical effect for one capability method, if defined."""

    return CAPABILITY_METHOD_EFFECTS.get(capability_type, {}).get(method)
