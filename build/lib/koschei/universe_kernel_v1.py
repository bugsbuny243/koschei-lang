"""Koschei Universe Kernel v1.

This is the technical binding layer between the small Koschei surface vocabulary
and the deeper library/runtime machinery. The words are not aliases for Python,
JavaScript, Rust, React, or another host technology. Each sigil denotes a bundle
of security semantics and obligations owned by Koschei itself.

The universe kernel deliberately uses original Koschei roles. Fictional universes
may inspire design discussions, but third-party characters/brands are not runtime
or language dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Iterable, Mapping

_CTX = b"koschei.universe-kernel/v1\x00"


class UniverseKernelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SigilSpec:
    sigil: str
    semantic_domain: str
    invariants: tuple[str, ...]
    activates: tuple[str, ...]
    obligations: tuple[str, ...]
    may_grant_authority: bool
    fail_closed: bool = True


@dataclass(frozen=True, slots=True)
class UniversePlan:
    sigils: tuple[str, ...]
    semantic_domains: tuple[str, ...]
    activated_modules: tuple[str, ...]
    obligations: tuple[str, ...]
    digest: str


_SIGILS = {
    "ka": SigilSpec(
        sigil="ka",
        semantic_domain="genesis.identity.integrity",
        invariants=(
            "identity-before-authority",
            "zero-ambient-authority-at-genesis",
            "source-and-object-integrity-before-execution",
            "canonical-state-has-one-identity",
            "unverified-input-cannot-become-trust-anchor",
        ),
        activates=(
            "koschei.integrity",
            "koschei.modules",
            "koschei.mir",
        ),
        obligations=(
            "establish-canonical-identity",
            "seal-integrity-lineage",
            "deny-ambient-authority",
        ),
        may_grant_authority=False,
    ),
    "vor": SigilSpec(
        sigil="vor",
        semantic_domain="authority.narrowing.effects",
        invariants=(
            "authority-must-be-explicit",
            "root-authority-must-narrow-before-io",
            "narrowed-authority-cannot-reexpand",
            "effect-identity-must-match-capability-operation",
            "runtime-authority-surface-must-match-canonical-contract",
        ),
        activates=(
            "koschei.capability_effect_contract_v1",
            "koschei.effect_contracts_v1",
            "koschei.effects",
            "koschei.runtime_capability_registry_v1",
            "koschei.runtime_boot_v1",
        ),
        obligations=(
            "derive-least-authority",
            "seal-effect-contract",
            "validate-runtime-before-authority-injection",
        ),
        may_grant_authority=True,
    ),
    "shi": SigilSpec(
        sigil="shi",
        semantic_domain="observation.evidence.attestation",
        invariants=(
            "claim-without-evidence-is-not-final",
            "writer-cannot-self-attest-final-effect",
            "independent-trust-domains-required-for-quorum",
            "conflicting-observation-fails-closed",
            "evidence-lineage-must-be-canonical",
        ),
        activates=(
            "koschei.library_effect_attestation_quorum_v0",
            "koschei.library_recovery_journal_v0",
        ),
        obligations=(
            "bind-observation-to-effect-receipt",
            "require-independent-evidence",
            "preserve-evidence-lineage",
        ),
        may_grant_authority=False,
    ),
    "thal": SigilSpec(
        sigil="thal",
        semantic_domain="containment.recovery.finality",
        invariants=(
            "containment-precedes-availability",
            "recovery-order-is-deterministic",
            "partial-commit-is-not-success",
            "stale-writer-is-fenced",
            "retries-cannot-duplicate-logical-effects",
            "split-brain-cannot-select-two-canonical-histories",
        ),
        activates=(
            "koschei.library_multi_scenario_containment_v0",
            "koschei.library_policy_conflict_resolution_v0",
            "koschei.library_recovery_transaction_v0",
            "koschei.library_recovery_replica_quorum_v0",
            "koschei.library_recovery_fencing_v0",
            "koschei.library_recovery_exactly_once_v0",
        ),
        obligations=(
            "derive-minimum-safe-containment",
            "fence-stale-writers",
            "commit-or-abort-recovery",
            "prove-exactly-once-effect-lineage",
        ),
        may_grant_authority=False,
    ),
    "nur": SigilSpec(
        sigil="nur",
        semantic_domain="visibility.knowledge-resistance.compartment",
        invariants=(
            "visibility-is-not-authority",
            "knowledge-acquisition-has-a-budget",
            "high-pressure-observation-reduces-visible-surface",
            "contained-state-exposes-zero-semantic-surface",
            "observer-aliases-may-rotate-without-changing-canonical-state",
        ),
        activates=(
            "koschei.library_adversary_learning_resistance_v0",
            "koschei.library_adaptive_visibility_v0",
        ),
        obligations=(
            "measure-knowledge-acquisition",
            "shrink-visibility-envelope",
            "rotate-observer-compartments",
            "preserve-canonical-state-behind-visibility",
        ),
        may_grant_authority=False,
    ),
}

SIGILS: Mapping[str, SigilSpec] = MappingProxyType(_SIGILS)
CANONICAL_SIGIL_ORDER = ("ka", "vor", "shi", "thal", "nur")


def sigil_spec(sigil: str) -> SigilSpec:
    try:
        return SIGILS[sigil]
    except KeyError as error:
        raise UniverseKernelError(f"unknown Koschei sigil: {sigil!r}") from error


def _canonical_digest(parts: Iterable[str]) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def compile_universe_plan(sigils: Iterable[str]) -> UniversePlan:
    """Compile a small sigil sequence into a deterministic deep-system plan.

    `ka` is the genesis boundary and therefore, when present with other sigils,
    must be first. Duplicate sigils are rejected because repeated spelling must
    not silently imply repeated authority or repeated side effects.
    """

    sequence = tuple(sigils)
    if not sequence:
        raise UniverseKernelError("universe plan requires at least one sigil")
    if len(sequence) != len(set(sequence)):
        raise UniverseKernelError("duplicate sigils are not canonical")
    for sigil in sequence:
        sigil_spec(sigil)
    if "ka" in sequence and len(sequence) > 1 and sequence[0] != "ka":
        raise UniverseKernelError("ka is the genesis boundary and must be first")

    specs = tuple(sigil_spec(sigil) for sigil in sequence)
    domains = tuple(spec.semantic_domain for spec in specs)
    activated = tuple(sorted({item for spec in specs for item in spec.activates}))
    obligations = tuple(sorted({item for spec in specs for item in spec.obligations}))

    digest_parts = ["sigils=" + ",".join(sequence)]
    digest_parts.extend("domain=" + domain for domain in domains)
    digest_parts.extend("module=" + item for item in activated)
    digest_parts.extend("obligation=" + item for item in obligations)
    for spec in specs:
        digest_parts.extend(
            f"invariant={spec.sigil}:{invariant}" for invariant in spec.invariants
        )
        digest_parts.append(
            f"authority={spec.sigil}:{int(spec.may_grant_authority)}"
        )
        digest_parts.append(f"fail_closed={spec.sigil}:{int(spec.fail_closed)}")

    return UniversePlan(
        sigils=sequence,
        semantic_domains=domains,
        activated_modules=activated,
        obligations=obligations,
        digest=_canonical_digest(digest_parts),
    )
