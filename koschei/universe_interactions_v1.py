"""Koschei Universe sigil composition rules v1.

Individual sigils describe local semantic domains. This module defines the new
obligations that emerge only when multiple Koschei domains are active together.
It is intentionally deterministic, defensive and fail-closed: composition never
creates hidden authority and never weakens an invariant owned by a component.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Iterable, Mapping

from .universe_kernel_v1 import UniversePlan, compile_universe_plan

_CTX = b"koschei.universe-interactions/v1\x00"


class UniverseInteractionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InteractionRule:
    rule_id: str
    requires: frozenset[str]
    invariants: tuple[str, ...]
    obligations: tuple[str, ...]
    may_grant_authority: bool = False
    fail_closed: bool = True


@dataclass(frozen=True, slots=True)
class ComposedUniversePlan:
    base: UniversePlan
    interaction_ids: tuple[str, ...]
    emergent_invariants: tuple[str, ...]
    emergent_obligations: tuple[str, ...]
    digest: str


_RULES = {
    "genesis-authority-seal": InteractionRule(
        rule_id="genesis-authority-seal",
        requires=frozenset({"ka", "vor"}),
        invariants=(
            "authority-lineage-must-descend-from-verified-genesis",
            "identity-change-invalidates-derived-authority",
        ),
        obligations=(
            "bind-authority-to-genesis-identity",
            "invalidate-authority-on-identity-drift",
        ),
    ),
    "identity-evidence-binding": InteractionRule(
        rule_id="identity-evidence-binding",
        requires=frozenset({"ka", "shi"}),
        invariants=(
            "evidence-without-canonical-subject-identity-is-not-final",
        ),
        obligations=(
            "bind-evidence-to-canonical-subject",
        ),
    ),
    "authority-evidence-provenance": InteractionRule(
        rule_id="authority-evidence-provenance",
        requires=frozenset({"ka", "vor", "shi"}),
        invariants=(
            "privileged-effect-must-prove-identity-authority-and-evidence-lineage",
            "attestation-cannot-upgrade-authority",
        ),
        obligations=(
            "seal-authorization-provenance",
            "prove-effect-authority-before-attestation-finality",
        ),
    ),
    "authority-visibility-separation": InteractionRule(
        rule_id="authority-visibility-separation",
        requires=frozenset({"vor", "nur"}),
        invariants=(
            "hidden-state-is-not-granted-authority",
            "visibility-expansion-cannot-expand-capability",
            "capability-expansion-cannot-bypass-visibility-policy",
        ),
        obligations=(
            "evaluate-authority-and-visibility-independently",
        ),
    ),
    "evidence-bound-recovery": InteractionRule(
        rule_id="evidence-bound-recovery",
        requires=frozenset({"shi", "thal"}),
        invariants=(
            "recovery-finality-requires-evidence-finality",
            "conflicting-evidence-blocks-recovery-commit",
        ),
        obligations=(
            "bind-recovery-commit-to-attested-effect",
            "abort-on-evidence-conflict",
        ),
    ),
    "non-escalating-recovery": InteractionRule(
        rule_id="non-escalating-recovery",
        requires=frozenset({"vor", "thal"}),
        invariants=(
            "recovery-cannot-create-authority-absent-before-failure",
            "replacement-writer-must-reenter-through-canonical-fencing",
        ),
        obligations=(
            "prove-recovery-authority-is-non-escalating",
        ),
    ),
    "private-observation-continuity": InteractionRule(
        rule_id="private-observation-continuity",
        requires=frozenset({"shi", "nur"}),
        invariants=(
            "evidence-continuity-must-survive-visibility-rotation",
            "attestation-cannot-force-broader-observer-visibility",
        ),
        obligations=(
            "preserve-evidence-through-compartment-rotation",
        ),
    ),
    "whole-universe-conservation": InteractionRule(
        rule_id="whole-universe-conservation",
        requires=frozenset({"ka", "vor", "shi", "thal", "nur"}),
        invariants=(
            "no-composition-may-create-ambient-authority",
            "no-composition-may-weaken-component-fail-closed-rules",
            "identity-authority-evidence-recovery-and-visibility-remain-separable",
        ),
        obligations=(
            "seal-whole-universe-conservation-proof",
        ),
    ),
}

INTERACTION_RULES: Mapping[str, InteractionRule] = MappingProxyType(_RULES)


def _digest(parts: Iterable[str]) -> str:
    return hashlib.sha256(_CTX + "\n".join(parts).encode("utf-8")).hexdigest()


def applicable_interactions(sigils: Iterable[str]) -> tuple[InteractionRule, ...]:
    active = frozenset(sigils)
    if not active:
        raise UniverseInteractionError("interaction graph requires at least one sigil")
    return tuple(
        rule
        for _, rule in sorted(INTERACTION_RULES.items())
        if rule.requires.issubset(active)
    )


def compose_universe(sigils: Iterable[str]) -> ComposedUniversePlan:
    """Compile sigils plus deterministic emergent interaction semantics."""

    sequence = tuple(sigils)
    base = compile_universe_plan(sequence)
    interactions = applicable_interactions(sequence)

    # Interaction rules are conservation rules. No interaction is allowed to
    # manufacture authority beyond what the base sigils already authorize.
    if any(rule.may_grant_authority for rule in interactions):
        raise UniverseInteractionError("interaction rule attempted to create authority")
    if any(not rule.fail_closed for rule in interactions):
        raise UniverseInteractionError("non-fail-closed interaction is not canonical")

    invariants = tuple(sorted({item for rule in interactions for item in rule.invariants}))
    obligations = tuple(sorted({item for rule in interactions for item in rule.obligations}))
    ids = tuple(rule.rule_id for rule in interactions)

    parts = [f"base={base.digest}"]
    parts.extend(f"interaction={item}" for item in ids)
    parts.extend(f"invariant={item}" for item in invariants)
    parts.extend(f"obligation={item}" for item in obligations)

    return ComposedUniversePlan(
        base=base,
        interaction_ids=ids,
        emergent_invariants=invariants,
        emergent_obligations=obligations,
        digest=_digest(parts),
    )
