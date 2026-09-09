"""Koschei Fabric v1 contract provider for Koschei Lang.

The provider is intentionally dependency-free and side-effect-free. It exposes
Lang-owned capability metadata without importing Koschei Web3 or Sentinel
internals, preserving the compiler/runtime project boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


FABRIC_SCHEMA_VERSION: Final = "1.0"
FABRIC_COMPONENT: Final = "koschei-lang"


@dataclass(frozen=True, slots=True)
class FabricCapabilityV1:
    id: str
    domain: str
    status: str
    backend: str
    frontend: str
    telemetry: str


@dataclass(frozen=True, slots=True)
class FabricComponentV1:
    schemaVersion: str
    component: str
    repository: str
    role: str
    preserveExisting: bool
    defaultMode: str
    breakingChangesAllowed: bool
    crossProjectAccess: str
    capabilities: tuple[FabricCapabilityV1, ...]


def fabric_component_v1() -> FabricComponentV1:
    """Return the immutable Lang-owned Fabric capability contract."""
    return FabricComponentV1(
        schemaVersion=FABRIC_SCHEMA_VERSION,
        component=FABRIC_COMPONENT,
        repository="bugsbuny243/koschei-lang",
        role="programmable-policy-agent-language",
        preserveExisting=True,
        defaultMode="observe",
        breakingChangesAllowed=False,
        crossProjectAccess="contract-only",
        capabilities=(
            FabricCapabilityV1(
                id="language-toolchain",
                domain="core",
                status="stable",
                backend="existing",
                frontend="existing",
                telemetry="existing",
            ),
            FabricCapabilityV1(
                id="web4-web6-policy-and-agent-profile",
                domain="web4",
                status="experimental",
                backend="adapter",
                frontend="planned",
                telemetry="planned",
            ),
        ),
    )


def fabric_component_payload_v1() -> dict[str, object]:
    """Return a JSON-serializable contract payload for external adapters."""
    return asdict(fabric_component_v1())


def require_safe_fabric_contract_v1(component: FabricComponentV1 | None = None) -> FabricComponentV1:
    """Fail closed if a future edit weakens the zero-rewrite integration rules."""
    value = component or fabric_component_v1()
    if value.schemaVersion != FABRIC_SCHEMA_VERSION:
        raise ValueError("unsupported Fabric schema version")
    if not value.preserveExisting:
        raise ValueError("Fabric contract must preserve existing Lang behavior")
    if value.breakingChangesAllowed:
        raise ValueError("Fabric contract must not permit breaking changes")
    if value.crossProjectAccess != "contract-only":
        raise ValueError("cross-project access must remain contract-only")
    if value.defaultMode not in {"observe", "shadow"}:
        raise ValueError("new Lang Fabric integration must start in observe/shadow mode")
    return value
