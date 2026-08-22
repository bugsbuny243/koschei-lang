"""Koschei Library semantic expansion engine v1.

The visible language is intentionally small.  This module turns a composed
Universe activation plan into an explicit Library work plan.  It does not execute
foreign frameworks or grant authority; it names the internal Koschei mechanisms
that must satisfy each semantic obligation before execution can proceed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Iterable, Mapping

from .universe_activation_engine_v1 import UniverseActivationPlan, compile_activation_plan

_CTX = b"koschei.library-expansion-engine/v1\x00"


class LibraryExpansionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LibraryBinding:
    obligation: str
    subsystem: str
    proof_kind: str
    grants_authority: bool = False


@dataclass(frozen=True, slots=True)
class LibraryExpansionStep:
    activation_step_id: str
    phase: str
    obligation: str
    subsystem: str
    proof_kind: str
    requires: tuple[str, ...]
    binding_digest: str


@dataclass(frozen=True, slots=True)
class LibraryExpansionPlan:
    activation_plan_digest: str
    sigils: tuple[str, ...]
    steps: tuple[LibraryExpansionStep, ...]
    digest: str


# Explicit obligation ownership.  Unknown obligations are rejected: the Library
# is not allowed to silently improvise semantics from string similarity.
_BINDINGS = {
    "establish-canonical-identity": LibraryBinding(
        "establish-canonical-identity", "library.identity_genesis", "identity-proof"
    ),
    "seal-integrity-lineage": LibraryBinding(
        "seal-integrity-lineage", "library.integrity_lineage", "integrity-seal"
    ),
    "deny-ambient-authority": LibraryBinding(
        "deny-ambient-authority", "library.zero_authority", "authority-absence-proof"
    ),
    "derive-least-authority": LibraryBinding(
        "derive-least-authority", "library.authority_derivation", "capability-proof", True
    ),
    "seal-effect-contract": LibraryBinding(
        "seal-effect-contract", "library.effect_contract", "effect-seal"
    ),
    "validate-runtime-before-authority-injection": LibraryBinding(
        "validate-runtime-before-authority-injection", "library.runtime_gate", "runtime-attestation"
    ),
    "bind-observation-to-effect-receipt": LibraryBinding(
        "bind-observation-to-effect-receipt", "library.evidence_binding", "effect-evidence"
    ),
    "require-independent-evidence": LibraryBinding(
        "require-independent-evidence", "library.attestation_quorum", "quorum-proof"
    ),
    "preserve-evidence-lineage": LibraryBinding(
        "preserve-evidence-lineage", "library.evidence_lineage", "lineage-proof"
    ),
    "derive-minimum-safe-containment": LibraryBinding(
        "derive-minimum-safe-containment", "library.containment", "containment-proof"
    ),
    "fence-stale-writers": LibraryBinding(
        "fence-stale-writers", "library.recovery_fencing", "fencing-proof"
    ),
    "commit-or-abort-recovery": LibraryBinding(
        "commit-or-abort-recovery", "library.recovery_transaction", "recovery-commit-proof"
    ),
    "prove-exactly-once-effect-lineage": LibraryBinding(
        "prove-exactly-once-effect-lineage", "library.exactly_once", "effect-receipt-proof"
    ),
    "measure-knowledge-acquisition": LibraryBinding(
        "measure-knowledge-acquisition", "library.knowledge_budget", "observation-budget-proof"
    ),
    "shrink-visibility-envelope": LibraryBinding(
        "shrink-visibility-envelope", "library.visibility_envelope", "visibility-policy-proof"
    ),
    "rotate-observer-compartments": LibraryBinding(
        "rotate-observer-compartments", "library.compartment_rotation", "rotation-proof"
    ),
    "preserve-canonical-state-behind-visibility": LibraryBinding(
        "preserve-canonical-state-behind-visibility", "library.canonical_state", "state-continuity-proof"
    ),
    "bind-authority-to-genesis-identity": LibraryBinding(
        "bind-authority-to-genesis-identity", "library.authority_lineage", "genesis-authority-proof"
    ),
    "invalidate-authority-on-identity-drift": LibraryBinding(
        "invalidate-authority-on-identity-drift", "library.authority_tombstone", "revocation-proof"
    ),
    "bind-evidence-to-canonical-subject": LibraryBinding(
        "bind-evidence-to-canonical-subject", "library.subject_evidence", "subject-binding-proof"
    ),
    "seal-authorization-provenance": LibraryBinding(
        "seal-authorization-provenance", "library.authorization_provenance", "authorization-proof"
    ),
    "prove-effect-authority-before-attestation-finality": LibraryBinding(
        "prove-effect-authority-before-attestation-finality", "library.effect_authority", "effect-authority-proof"
    ),
    "evaluate-authority-and-visibility-independently": LibraryBinding(
        "evaluate-authority-and-visibility-independently", "library.authority_visibility_separation", "separation-proof"
    ),
    "bind-recovery-commit-to-attested-effect": LibraryBinding(
        "bind-recovery-commit-to-attested-effect", "library.recovery_attestation", "attested-recovery-proof"
    ),
    "abort-on-evidence-conflict": LibraryBinding(
        "abort-on-evidence-conflict", "library.evidence_conflict_gate", "conflict-proof"
    ),
    "prove-recovery-authority-is-non-escalating": LibraryBinding(
        "prove-recovery-authority-is-non-escalating", "library.recovery_authority", "non-escalation-proof"
    ),
    "preserve-evidence-through-compartment-rotation": LibraryBinding(
        "preserve-evidence-through-compartment-rotation", "library.private_evidence_continuity", "continuity-proof"
    ),
    "seal-whole-universe-conservation-proof": LibraryBinding(
        "seal-whole-universe-conservation-proof", "library.universe_conservation", "universe-conservation-proof"
    ),
}

LIBRARY_BINDINGS: Mapping[str, LibraryBinding] = MappingProxyType(_BINDINGS)


def _binding_digest(step_id: str, binding: LibraryBinding) -> str:
    payload = "|".join(
        (
            step_id,
            binding.obligation,
            binding.subsystem,
            binding.proof_kind,
            str(int(binding.grants_authority)),
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def compile_library_expansion(sigils: Iterable[str]) -> LibraryExpansionPlan:
    activation = compile_activation_plan(tuple(sigils))
    expanded: list[LibraryExpansionStep] = []

    for step in activation.steps:
        binding = LIBRARY_BINDINGS.get(step.obligation)
        if binding is None:
            raise LibraryExpansionError(
                f"unbound Koschei Library obligation: {step.obligation}"
            )
        expanded.append(
            LibraryExpansionStep(
                activation_step_id=step.step_id,
                phase=step.phase,
                obligation=step.obligation,
                subsystem=binding.subsystem,
                proof_kind=binding.proof_kind,
                requires=step.requires,
                binding_digest=_binding_digest(step.step_id, binding),
            )
        )

    authority_bindings = [
        item for item in expanded if LIBRARY_BINDINGS[item.obligation].grants_authority
    ]
    if any(item.obligation != "derive-least-authority" for item in authority_bindings):
        raise LibraryExpansionError("non-canonical Library binding attempted to grant authority")

    parts = [f"activation={activation.digest}"]
    parts.extend(
        "step=" + "|".join(
            (
                item.activation_step_id,
                item.phase,
                item.obligation,
                item.subsystem,
                item.proof_kind,
                ",".join(item.requires),
                item.binding_digest,
            )
        )
        for item in expanded
    )
    digest = hashlib.sha256(_CTX + "\n".join(parts).encode("utf-8")).hexdigest()
    return LibraryExpansionPlan(
        activation_plan_digest=activation.digest,
        sigils=activation.composed.base.sigils,
        steps=tuple(expanded),
        digest=digest,
    )
