"""Koschei Fabric v1 contract provider for Koschei Lang.

The provider is intentionally dependency-free and side-effect-free. It exposes
Lang-owned capability metadata without importing Koschei Web3 or Sentinel
internals, preserving the compiler/runtime project boundary.

`fabric/component.json` is the operator-facing canonical capability inventory.
This provider mirrors its security-relevant status fields while retaining one
legacy capability id as an explicit compatibility alias instead of silently
breaking existing consumers.
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
    evidenceState: str = "unverified"
    workPackages: tuple[str, ...] = ()
    notes: str = ""
    compatibilityAliasFor: str | None = None


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
    legacyInterfaces: str = "preserve"


def _canonical_capabilities() -> tuple[FabricCapabilityV1, ...]:
    return (
        FabricCapabilityV1(
            id="language-toolchain",
            domain="core",
            status="experimental",
            evidenceState="blocked",
            workPackages=("LANG-01", "LANG-02", "LANG-03", "LANG-04", "SUPPLY-02"),
            backend="existing",
            frontend="existing",
            telemetry="existing",
            notes=(
                "Parser/compiler/runtime work exists, but canonical execution, public CLI transition, "
                "broker/worker OS isolation and independent release-root acceptance remain explicit P0 gates."
            ),
        ),
        FabricCapabilityV1(
            id="authorization-transition-ir",
            domain="web4",
            status="experimental",
            evidenceState="partial",
            workPackages=("AGENT-02", "AGENT-04", "LANG-01", "LANG-02"),
            backend="existing",
            frontend="planned",
            telemetry="planned",
            notes=(
                "Provider-independent AuthorizationState/AuthorizationTransition, eight-axis attenuation, "
                "VALID_PARENT_NOW and execution-time authorization snapshots are present on main. Fresh "
                "effect authorization binding remains a separate draft integration candidate and is not "
                "counted as accepted here. Durable shared monotonic state, broker/worker OS confinement "
                "and T01-T14 acceptance remain open."
            ),
        ),
        FabricCapabilityV1(
            id="web4-policy-agent-profile",
            domain="web4",
            status="experimental",
            evidenceState="research",
            workPackages=("AGENT-02", "AGENT-04", "LANG-03", "LANG-04"),
            backend="adapter",
            frontend="planned",
            telemetry="planned",
            notes=(
                "Exposes Lang-owned authority, delegation, budget and effect-receipt semantics to Fabric "
                "through explicit adapters. External model/tool metadata cannot define Lang authority."
            ),
        ),
        FabricCapabilityV1(
            id="web5-identity-data-profile",
            domain="web5",
            status="planned",
            evidenceState="unverified",
            workPackages=("ID-01", "ID-02", "ID-03", "ID-04", "DATA-04"),
            backend="planned",
            frontend="planned",
            telemetry="planned",
            notes=(
                "Tracks future DID, credential, revocation and user-controlled-data adapters without "
                "claiming completed Web5 product support."
            ),
        ),
    )


def fabric_component_v1() -> FabricComponentV1:
    """Return the immutable Lang-owned Fabric capability contract."""
    canonical = _canonical_capabilities()
    legacy_alias = FabricCapabilityV1(
        id="web4-web6-policy-and-agent-profile",
        domain="web4",
        status="experimental",
        evidenceState="research",
        workPackages=("AGENT-02", "AGENT-04", "LANG-03", "LANG-04"),
        backend="adapter",
        frontend="planned",
        telemetry="planned",
        notes="Compatibility alias only; canonical capability id is web4-policy-agent-profile.",
        compatibilityAliasFor="web4-policy-agent-profile",
    )
    return FabricComponentV1(
        schemaVersion=FABRIC_SCHEMA_VERSION,
        component=FABRIC_COMPONENT,
        repository="bugsbuny243/koschei-lang",
        role="programmable-policy-agent-language",
        preserveExisting=True,
        defaultMode="observe",
        breakingChangesAllowed=False,
        crossProjectAccess="contract-only",
        legacyInterfaces="preserve",
        capabilities=canonical + (legacy_alias,),
    )


def fabric_component_payload_v1() -> dict[str, object]:
    """Return a JSON-serializable contract payload for external adapters."""
    return asdict(fabric_component_v1())


def require_safe_fabric_contract_v1(component: FabricComponentV1 | None = None) -> FabricComponentV1:
    """Fail closed if a future edit weakens zero-rewrite or evidence-maturity rules."""
    value = component or fabric_component_v1()
    if value.schemaVersion != FABRIC_SCHEMA_VERSION:
        raise ValueError("unsupported Fabric schema version")
    if not value.preserveExisting:
        raise ValueError("Fabric contract must preserve existing Lang behavior")
    if value.breakingChangesAllowed:
        raise ValueError("Fabric contract must not permit breaking changes")
    if value.crossProjectAccess != "contract-only":
        raise ValueError("cross-project access must remain contract-only")
    if value.legacyInterfaces != "preserve":
        raise ValueError("legacy Fabric interfaces must remain preserved")
    if value.defaultMode not in {"observe", "shadow"}:
        raise ValueError("new Lang Fabric integration must start in observe/shadow mode")

    capabilities = {item.id: item for item in value.capabilities}
    toolchain = capabilities.get("language-toolchain")
    if toolchain is None or toolchain.status != "experimental" or toolchain.evidenceState != "blocked":
        raise ValueError("blocked Lang toolchain must not be advertised as stable")
    transition = capabilities.get("authorization-transition-ir")
    if transition is None or transition.evidenceState != "partial":
        raise ValueError("authorization-transition-ir evidence maturity must remain explicit")
    alias = capabilities.get("web4-web6-policy-and-agent-profile")
    if alias is None or alias.compatibilityAliasFor != "web4-policy-agent-profile":
        raise ValueError("legacy Web4/Web6 capability id must remain an explicit compatibility alias")
    return value
