"""Deterministic Koschei survival-branch selection v1.

This is the first technical form of the design metaphor previously described as
survival-branch/Doctor-Strange reasoning. It is not an AI oracle and grants no
authority. Candidate futures carry explicit loss metrics. Branches that weaken
Khar or exceed hard safety ceilings are impossible; remaining branches are
ranked by a deterministic objective and sealed into a decision.

The selected branch is only a plan commitment. Execution still requires the
normal Galaxy constitutional gate and an exact-event Sathra.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string
from typing import Iterable

_CTX = b"koschei.survival-branch/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class SurvivalBranchError(ValueError):
    pass


def _d64(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise SurvivalBranchError(f"{label} must be a 64-character digest")
    value = value.lower()
    if any(ch not in _HEX for ch in value) or value == "0" * 64:
        raise SurvivalBranchError(f"{label} must be a non-zero hexadecimal digest")
    return value


def _metric(value: int, label: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 1000:
        raise SurvivalBranchError(f"{label} must be in 0..1000")
    return value


@dataclass(frozen=True, slots=True)
class SurvivalBranch:
    branch_digest: str
    action_commitment_digest: str
    khar_preserved: bool
    authority_escape: int
    cross_domain_spread: int
    evidence_loss: int
    irreversible_loss: int
    availability_loss: int
    recoverability: int

    def __post_init__(self) -> None:
        _d64(self.branch_digest, "branch_digest")
        _d64(self.action_commitment_digest, "action_commitment_digest")
        if not isinstance(self.khar_preserved, bool):
            raise SurvivalBranchError("khar_preserved must be boolean")
        for name in (
            "authority_escape",
            "cross_domain_spread",
            "evidence_loss",
            "irreversible_loss",
            "availability_loss",
            "recoverability",
        ):
            _metric(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class SurvivalObjective:
    max_authority_escape: int = 0
    max_cross_domain_spread: int = 0
    max_evidence_loss: int = 100
    irreversible_loss_weight: int = 8
    availability_loss_weight: int = 1
    evidence_loss_weight: int = 10
    cross_domain_spread_weight: int = 20
    recoverability_weight: int = 4

    def __post_init__(self) -> None:
        for name in ("max_authority_escape", "max_cross_domain_spread", "max_evidence_loss"):
            _metric(getattr(self, name), name)
        for name in (
            "irreversible_loss_weight",
            "availability_loss_weight",
            "evidence_loss_weight",
            "cross_domain_spread_weight",
            "recoverability_weight",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0 or value > 1_000_000:
                raise SurvivalBranchError(f"{name} must be a non-negative bounded integer")

    @property
    def digest(self) -> str:
        rows = tuple(f"{name}={getattr(self, name)}" for name in self.__dataclass_fields__)
        return hashlib.sha256(_CTX + b"objective\x00" + "\n".join(rows).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SurvivalBranchDecision:
    chosen_branch_digest: str
    chosen_action_commitment_digest: str
    objective_digest: str
    eligible_branch_digests: tuple[str, ...]
    rejected_branch_digests: tuple[str, ...]
    chosen_score: int
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        _d64(self.chosen_branch_digest, "chosen_branch_digest")
        _d64(self.chosen_action_commitment_digest, "chosen_action_commitment_digest")
        _d64(self.objective_digest, "objective_digest")
        if self.chosen_branch_digest not in self.eligible_branch_digests:
            raise SurvivalBranchError("chosen branch is not eligible")
        if set(self.eligible_branch_digests) & set(self.rejected_branch_digests):
            raise SurvivalBranchError("branch cannot be both eligible and rejected")
        if self.chosen_score < 0:
            raise SurvivalBranchError("survival score cannot be negative")
        expected = _decision_digest(
            self.chosen_branch_digest,
            self.chosen_action_commitment_digest,
            self.objective_digest,
            self.eligible_branch_digests,
            self.rejected_branch_digests,
            self.chosen_score,
        )
        if self.digest != expected:
            raise SurvivalBranchError("survival branch decision seal mismatch")


def _score(branch: SurvivalBranch, objective: SurvivalObjective) -> int:
    return (
        branch.irreversible_loss * objective.irreversible_loss_weight
        + branch.availability_loss * objective.availability_loss_weight
        + branch.evidence_loss * objective.evidence_loss_weight
        + branch.cross_domain_spread * objective.cross_domain_spread_weight
        + (1000 - branch.recoverability) * objective.recoverability_weight
    )


def _eligible(branch: SurvivalBranch, objective: SurvivalObjective) -> bool:
    return (
        branch.khar_preserved
        and branch.authority_escape <= objective.max_authority_escape
        and branch.cross_domain_spread <= objective.max_cross_domain_spread
        and branch.evidence_loss <= objective.max_evidence_loss
    )


def _decision_digest(
    chosen: str,
    action: str,
    objective: str,
    eligible: tuple[str, ...],
    rejected: tuple[str, ...],
    score: int,
) -> str:
    rows = [
        f"chosen={chosen}",
        f"action={action}",
        f"objective={objective}",
        f"score={score}",
        "eligible=" + ",".join(eligible),
        "rejected=" + ",".join(rejected),
    ]
    return hashlib.sha256(_CTX + b"decision\x00" + "\n".join(rows).encode()).hexdigest()


def select_survival_branch(
    branches: Iterable[SurvivalBranch],
    *,
    objective: SurvivalObjective | None = None,
) -> SurvivalBranchDecision:
    """Choose the least-loss eligible future using deterministic Khar constraints."""

    objective = objective or SurvivalObjective()
    supplied = tuple(branches)
    if not supplied:
        raise SurvivalBranchError("survival selection requires candidate branches")
    digests = [branch.branch_digest for branch in supplied]
    if len(set(digests)) != len(digests):
        raise SurvivalBranchError("duplicate survival branch identity")

    eligible = tuple(branch for branch in supplied if _eligible(branch, objective))
    rejected = tuple(branch for branch in supplied if not _eligible(branch, objective))
    if not eligible:
        raise SurvivalBranchError(
            "no branch preserves Khar within hard survival ceilings"
        )

    ranked = sorted(eligible, key=lambda branch: (_score(branch, objective), branch.branch_digest))
    chosen = ranked[0]
    eligible_digests = tuple(sorted(branch.branch_digest for branch in eligible))
    rejected_digests = tuple(sorted(branch.branch_digest for branch in rejected))
    score = _score(chosen, objective)
    result = SurvivalBranchDecision(
        chosen_branch_digest=chosen.branch_digest,
        chosen_action_commitment_digest=chosen.action_commitment_digest,
        objective_digest=objective.digest,
        eligible_branch_digests=eligible_digests,
        rejected_branch_digests=rejected_digests,
        chosen_score=score,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _decision_digest(
            result.chosen_branch_digest,
            result.chosen_action_commitment_digest,
            result.objective_digest,
            result.eligible_branch_digests,
            result.rejected_branch_digests,
            result.chosen_score,
        ),
    )
    result.assert_sealed()
    return result
