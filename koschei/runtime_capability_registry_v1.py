"""Runtime capability registry derived from Koschei's canonical authority contract.

The tree-walking interpreter owns implementations, not language authority.  This
module turns the canonical capability contract into a runtime-facing registry and
validates that an implementation module exposes exactly the required authority
surface before it is trusted as a Koschei runtime.

Keeping this adapter outside ``interpreter.py`` avoids making the runtime class
layout a second source of truth and gives native/alternate runtimes the same
validation target.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Mapping

from .capability_effect_contract_v1 import (
    CAPABILITY_METHOD_EFFECTS,
    NARROWED_OPERATIONS,
    NET_ORIGIN_SCHEMES,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)


@dataclass(frozen=True, slots=True)
class RuntimeCapabilitySpec:
    capability_type: str
    methods: frozenset[str]
    effects: Mapping[str, str]
    is_root: bool


@dataclass(frozen=True, slots=True)
class RuntimeCapabilityRegistry:
    system_members: Mapping[str, str]
    capabilities: Mapping[str, RuntimeCapabilitySpec]
    network_origin_schemes: frozenset[str]


def canonical_runtime_registry() -> RuntimeCapabilityRegistry:
    """Build the runtime view from the single canonical language contract."""

    capabilities: dict[str, RuntimeCapabilitySpec] = {}
    for capability_type, methods in ROOT_NARROWING.items():
        capabilities[capability_type] = RuntimeCapabilitySpec(
            capability_type=capability_type,
            methods=frozenset(methods),
            effects=CAPABILITY_METHOD_EFFECTS[capability_type],
            is_root=True,
        )
    for capability_type, methods in NARROWED_OPERATIONS.items():
        capabilities[capability_type] = RuntimeCapabilitySpec(
            capability_type=capability_type,
            methods=frozenset(methods),
            effects=CAPABILITY_METHOD_EFFECTS[capability_type],
            is_root=False,
        )
    return RuntimeCapabilityRegistry(
        system_members=SYSTEM_CAPABILITY_MEMBERS,
        capabilities=capabilities,
        network_origin_schemes=NET_ORIGIN_SCHEMES,
    )


def validate_runtime_module(runtime: ModuleType) -> RuntimeCapabilityRegistry:
    """Fail closed if a runtime implementation drifts from the language contract.

    Extra public methods are deliberately not rejected here: implementation
    helpers may exist, but every language-visible capability member and operation
    must exist and be callable.  SystemCaps' slots are checked exactly because
    those names are the language-visible root authority surface.
    """

    registry = canonical_runtime_registry()

    system_type = getattr(runtime, "SystemCaps", None)
    if system_type is None:
        raise RuntimeError("Koschei runtime SystemCaps implementasyonu eksik")
    slots = frozenset(getattr(system_type, "__slots__", ()))
    expected_slots = frozenset(registry.system_members)
    if slots != expected_slots:
        raise RuntimeError(
            "Koschei runtime SystemCaps yüzeyi canonical contract'tan saptı: "
            f"expected={sorted(expected_slots)}, actual={sorted(slots)}"
        )

    for member, root_type in registry.system_members.items():
        if not hasattr(runtime, root_type):
            raise RuntimeError(
                f"Koschei runtime '{member}' için {root_type} implementasyonu eksik"
            )

    for capability_type, spec in registry.capabilities.items():
        runtime_type = getattr(runtime, capability_type, None)
        if runtime_type is None:
            raise RuntimeError(
                f"Koschei runtime capability implementasyonu eksik: {capability_type}"
            )
        for method in spec.methods:
            if not callable(getattr(runtime_type, method, None)):
                raise RuntimeError(
                    "Koschei runtime canonical capability metodunu uygulamıyor: "
                    f"{capability_type}.{method}"
                )
        if frozenset(spec.effects) != spec.methods:
            raise RuntimeError(
                "Canonical runtime registry effect yüzeyi method yüzeyiyle uyuşmuyor: "
                f"{capability_type}"
            )

    runtime_schemes = getattr(runtime, "ALLOWED_NET_SCHEMES", None)
    if runtime_schemes is not None and frozenset(runtime_schemes) != registry.network_origin_schemes:
        raise RuntimeError(
            "Koschei runtime network authority policy canonical contract'tan saptı"
        )

    return registry
