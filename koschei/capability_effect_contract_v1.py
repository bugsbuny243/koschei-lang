"""Canonical capability contract for Koschei.

This module is the single source of truth for capability shape, capability
method effect names, capability-boundary policy constants, and the power domain
occupied by each canonical capability/effect. Typed HIR helpers, source-level
effect checking and MIR sealing consume this contract rather than maintaining
parallel taxonomies.

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
PERSIST_READ = "persist.read"
PERSIST_WRITE = "persist.write"

POWER_DOMAIN_IDENTITY = "identity"
POWER_DOMAIN_AUTHORITY = "authority"
POWER_DOMAIN_DATA = "data"
POWER_DOMAIN_COMPUTE = "compute"
POWER_DOMAIN_NETWORK = "network"
POWER_DOMAIN_CONTINUITY = "continuity"
CANONICAL_POWER_DOMAINS = frozenset(
    {
        POWER_DOMAIN_IDENTITY,
        POWER_DOMAIN_AUTHORITY,
        POWER_DOMAIN_DATA,
        POWER_DOMAIN_COMPUTE,
        POWER_DOMAIN_NETWORK,
        POWER_DOMAIN_CONTINUITY,
    }
)

# Network authority may only be narrowed to explicit HTTP(S) origins. This is a
# language-level authority rule, not a parser/runtime implementation detail.
NET_ORIGIN_SCHEMES = frozenset({"http", "https"})

_SYSTEM_CAPABILITY_MEMBERS = {
    "net": "NetRoot",
    "disk": "DiskRoot",
    "env": "EnvRoot",
    "process": "ProcessRoot",
    "persist": "PersistRoot",
}

_ROOT_NARROWING = {
    "NetRoot": {"allow": "NetCaps"},
    "DiskRoot": {"allow": "DiskCaps", "allow_read_only": "DiskReadCaps"},
    "EnvRoot": {"allow": "EnvCaps"},
    "ProcessRoot": {"allow": "ProcessCaps"},
    "PersistRoot": {"allow": "PersistCaps"},
}

_NARROWED_OPERATIONS = {
    "NetCaps": {"get", "post", "put", "delete", "request"},
    "DiskCaps": {"read", "write", "delete", "list", "read_file", "write_file"},
    "DiskReadCaps": {"read", "list", "read_file"},
    "EnvCaps": {"get"},
    "ProcessCaps": {"run", "spawn"},
    "PersistCaps": {"load", "commit"},
}

_CAPABILITY_METHOD_EFFECTS = {
    "NetRoot": {"allow": AUTHORITY_DERIVE},
    "DiskRoot": {
        "allow": AUTHORITY_DERIVE,
        "allow_read_only": AUTHORITY_DERIVE,
    },
    "EnvRoot": {"allow": AUTHORITY_DERIVE},
    "ProcessRoot": {"allow": AUTHORITY_DERIVE},
    "PersistRoot": {"allow": AUTHORITY_DERIVE},
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
    "PersistCaps": {"load": PERSIST_READ, "commit": PERSIST_WRITE},
}

# Power domains classify existing capability/effect semantics. They are not a
# second grant system. In particular, no mapping below can authorize anything.
# The mapping exists so request-bound execution can fail closed if a future
# capability-contract edit accidentally crosses from one power domain to another.
_CAPABILITY_POWER_DOMAINS = {
    "SystemCaps": POWER_DOMAIN_AUTHORITY,
    "NetRoot": POWER_DOMAIN_NETWORK,
    "NetCaps": POWER_DOMAIN_NETWORK,
    "DiskRoot": POWER_DOMAIN_DATA,
    "DiskCaps": POWER_DOMAIN_DATA,
    "DiskReadCaps": POWER_DOMAIN_DATA,
    "EnvRoot": POWER_DOMAIN_DATA,
    "EnvCaps": POWER_DOMAIN_DATA,
    "ProcessRoot": POWER_DOMAIN_COMPUTE,
    "ProcessCaps": POWER_DOMAIN_COMPUTE,
    "PersistRoot": POWER_DOMAIN_CONTINUITY,
    "PersistCaps": POWER_DOMAIN_CONTINUITY,
}

_EFFECT_POWER_DOMAINS = {
    NET_IO: POWER_DOMAIN_NETWORK,
    DISK_READ: POWER_DOMAIN_DATA,
    DISK_WRITE: POWER_DOMAIN_DATA,
    ENV_READ: POWER_DOMAIN_DATA,
    PROCESS_EXEC: POWER_DOMAIN_COMPUTE,
    PERSIST_READ: POWER_DOMAIN_CONTINUITY,
    PERSIST_WRITE: POWER_DOMAIN_CONTINUITY,
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
CAPABILITY_POWER_DOMAINS: Mapping[str, str] = MappingProxyType(
    dict(_CAPABILITY_POWER_DOMAINS)
)
EFFECT_POWER_DOMAINS: Mapping[str, str] = MappingProxyType(
    dict(_EFFECT_POWER_DOMAINS)
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


class CapabilityPowerDomainError(ValueError):
    pass


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


def power_domain_for_capability_type(capability_type: str) -> str | None:
    """Return the power domain occupied by one canonical capability type."""

    return CAPABILITY_POWER_DOMAINS.get(capability_type)


def power_domain_for_effect(
    effect: str,
    *,
    capability_type: str | None = None,
) -> str | None:
    """Return the power domain occupied by one canonical capability effect.

    `authority.derive` is intentionally relative to its source capability. A
    NetRoot narrowing operation remains in the network power domain; a DiskRoot
    narrowing operation remains in the data power domain. Treating all narrowing
    as a move into one ambient `authority` domain would itself create escalation.
    """

    if effect == AUTHORITY_DERIVE:
        if capability_type is None:
            return None
        return power_domain_for_capability_type(capability_type)
    return EFFECT_POWER_DOMAINS.get(effect)


def capability_method_stays_within_power_domain(
    capability_type: str,
    method: str,
) -> bool:
    """Return whether one canonical capability method stays in its own domain.

    Unknown capability/method/effect/domain combinations fail closed by returning
    False. This function grants no authority; it is a negative security invariant.
    """

    effect = effect_for(capability_type, method)
    if effect is None:
        return False
    source_domain = power_domain_for_capability_type(capability_type)
    target_domain = power_domain_for_effect(
        effect,
        capability_type=capability_type,
    )
    return (
        source_domain is not None
        and target_domain is not None
        and source_domain == target_domain
    )


def require_capability_method_same_power_domain(
    capability_type: str,
    method: str,
) -> tuple[str, str]:
    """Return `(effect, domain)` or reject cross-domain/unknown authority drift."""

    effect = effect_for(capability_type, method)
    if effect is None:
        raise CapabilityPowerDomainError(
            "unknown capability method cannot cross the power-domain boundary"
        )
    source_domain = power_domain_for_capability_type(capability_type)
    target_domain = power_domain_for_effect(
        effect,
        capability_type=capability_type,
    )
    if source_domain is None or target_domain is None:
        raise CapabilityPowerDomainError(
            "unclassified capability effect cannot cross the power-domain boundary"
        )
    if source_domain != target_domain:
        raise CapabilityPowerDomainError(
            "cross-domain capability escalation denied: "
            f"{source_domain} -> {target_domain}"
        )
    return effect, source_domain
