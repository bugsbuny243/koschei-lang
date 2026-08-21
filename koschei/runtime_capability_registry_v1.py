"""Runtime capability registry derived from Koschei's canonical authority contract.

The tree-walking interpreter owns implementations, not language authority. This
module turns the canonical capability contract into a runtime-facing registry,
resolves runtime capability classes from canonical type names, and validates
that an implementation module exposes the required authority surface before it
is trusted as a Koschei runtime.

Keeping this adapter outside ``interpreter.py`` avoids making the runtime class
layout a second source of truth and gives native/alternate runtimes the same
validation target.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType, ModuleType
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

    @property
    def capability_type_names(self) -> frozenset[str]:
        """All canonical runtime-visible authority type names, including SystemCaps."""

        return frozenset({"SystemCaps", *self.capabilities})


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
        capabilities=MappingProxyType(capabilities),
        network_origin_schemes=NET_ORIGIN_SCHEMES,
    )


def runtime_capability_types(runtime: ModuleType) -> Mapping[str, type]:
    """Resolve canonical authority type names to concrete runtime classes.

    The names come only from the canonical registry. Runtime code therefore does
    not get to invent a second capability type taxonomy merely by defining a new
    class. Missing or non-type bindings fail closed.
    """

    registry = canonical_runtime_registry()
    resolved: dict[str, type] = {}
    for type_name in sorted(registry.capability_type_names):
        runtime_type = getattr(runtime, type_name, None)
        if not isinstance(runtime_type, type):
            raise RuntimeError(
                f"Koschei runtime canonical capability type binding eksik/geçersiz: {type_name}"
            )
        resolved[type_name] = runtime_type
    return MappingProxyType(resolved)


def capability_type_name_for_value(runtime: ModuleType, value: object) -> str | None:
    """Return canonical capability type name for a runtime value, if it is one."""

    for type_name, runtime_type in runtime_capability_types(runtime).items():
        if isinstance(value, runtime_type):
            return type_name
    return None


def value_matches_capability_type(
    runtime: ModuleType,
    value: object,
    expected_type_name: str,
) -> bool:
    """Match one value against a canonical authority type without hard-coded chains."""

    runtime_type = runtime_capability_types(runtime).get(expected_type_name)
    return runtime_type is not None and isinstance(value, runtime_type)


def validate_runtime_module(runtime: ModuleType) -> RuntimeCapabilityRegistry:
    """Fail closed if a runtime implementation drifts from the language contract.

    Extra public methods are deliberately not rejected here: implementation
    helpers may exist, but every language-visible capability member and operation
    must exist and be callable. SystemCaps' slots are checked exactly because
    those names are the language-visible root authority surface.
    """

    registry = canonical_runtime_registry()
    runtime_types = runtime_capability_types(runtime)

    system_type = runtime_types["SystemCaps"]
    slots = frozenset(getattr(system_type, "__slots__", ()))
    expected_slots = frozenset(registry.system_members)
    if slots != expected_slots:
        raise RuntimeError(
            "Koschei runtime SystemCaps yüzeyi canonical contract'tan saptı: "
            f"expected={sorted(expected_slots)}, actual={sorted(slots)}"
        )

    for member, root_type in registry.system_members.items():
        if root_type not in runtime_types:
            raise RuntimeError(
                f"Koschei runtime '{member}' için {root_type} implementasyonu eksik"
            )

    for capability_type, spec in registry.capabilities.items():
        runtime_type = runtime_types[capability_type]
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
