"""Khar-bounded autonomous survival proposals v1.

This is the first native Koschei form of bounded autonomous orchestration.  An
automated subsystem may rank already-described survival branches, but it cannot
rewrite Khar, create a new objective after selection, manufacture authority, or
execute an effect by itself.

The result is an authority-free proposal carrying the exact sealed
SurvivalBranchDecision produced by the deterministic survival selector.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .survival_branch_v1 import (
    SurvivalBranch,
    SurvivalBranchDecision,
    SurvivalObjective,
    select_survival_branch,
)

_CTX = b"koschei.bounded-autonomy/v1\x00"


class BoundedAutonomyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AutonomyBounds:
    max_candidates: int = 32
    max_proposal_round: int = 1_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.max_candidates, int) or not 1 <= self.max_candidates <= 1024:
            raise BoundedAutonomyError("max_candidates must be in 1..1024")
        if not isinstance(self.max_proposal_round, int) or not 0 <= self.max_proposal_round <= 1_000_000_000:
            raise BoundedAutonomyError("max_proposal_round is outside bounded range")

    @property
    def digest(self) -> str:
        payload = f"max_candidates={self.max_candidates}\nmax_round={self.max_proposal_round}".encode()
        return hashlib.sha256(_CTX + b"bounds\x00" + payload).hexdigest()


@dataclass(frozen=True, slots=True)
class BoundedAutonomyProposal:
    decision: SurvivalBranchDecision
    candidate_branch_digests: tuple[str, ...]
    objective_digest: str
    bounds_digest: str
    proposal_round: int
    evidence_digest: str
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        *,
        branches: tuple[SurvivalBranch, ...],
        objective: SurvivalObjective,
        bounds: AutonomyBounds,
    ) -> None:
        if self.authority:
            raise BoundedAutonomyError("bounded autonomy proposal cannot carry authority")
        if not isinstance(self.proposal_round, int) or not 0 <= self.proposal_round <= bounds.max_proposal_round:
            raise BoundedAutonomyError("proposal round exceeds autonomy bounds")
        if not self.evidence_digest or len(self.evidence_digest) != 64:
            raise BoundedAutonomyError("autonomy proposal requires a 64-character evidence digest")
        supplied = tuple(branches)
        if not supplied or len(supplied) > bounds.max_candidates:
            raise BoundedAutonomyError("candidate count exceeds autonomy bounds")
        canonical_candidates = tuple(sorted(branch.branch_digest for branch in supplied))
        if len(set(canonical_candidates)) != len(canonical_candidates):
            raise BoundedAutonomyError("duplicate autonomous candidate branch")
        if self.candidate_branch_digests != canonical_candidates:
            raise BoundedAutonomyError("autonomy proposal candidate set mismatch")
        if self.objective_digest != objective.digest:
            raise BoundedAutonomyError("autonomy proposal objective mismatch")
        if self.bounds_digest != bounds.digest:
            raise BoundedAutonomyError("autonomy proposal bounds mismatch")

        # Re-run the deterministic selector.  The autonomous layer cannot smuggle
        # in a different chosen future than the same Khar-bound inputs produce.
        expected_decision = select_survival_branch(supplied, objective=objective)
        self.decision.assert_sealed()
        if self.decision != expected_decision:
            raise BoundedAutonomyError("autonomy proposal decision diverges from Khar-bound selector")
        expected = _proposal_digest(
            decision_digest=self.decision.digest,
            candidates=self.candidate_branch_digests,
            objective_digest=self.objective_digest,
            bounds_digest=self.bounds_digest,
            proposal_round=self.proposal_round,
            evidence_digest=self.evidence_digest,
        )
        if self.digest != expected:
            raise BoundedAutonomyError("autonomy proposal seal mismatch")


def _proposal_digest(
    *,
    decision_digest: str,
    candidates: tuple[str, ...],
    objective_digest: str,
    bounds_digest: str,
    proposal_round: int,
    evidence_digest: str,
) -> str:
    rows = (
        f"decision={decision_digest}",
        "candidates=" + ",".join(candidates),
        f"objective={objective_digest}",
        f"bounds={bounds_digest}",
        f"round={proposal_round}",
        f"evidence={evidence_digest}",
    )
    return hashlib.sha256(_CTX + b"proposal\x00" + "\n".join(rows).encode()).hexdigest()


def propose_bounded_survival(
    branches: Iterable[SurvivalBranch],
    *,
    objective: SurvivalObjective | None = None,
    bounds: AutonomyBounds | None = None,
    proposal_round: int,
    evidence_digest: str,
) -> BoundedAutonomyProposal:
    """Produce one sealed authority-free survival proposal within explicit bounds."""

    supplied = tuple(branches)
    objective = objective or SurvivalObjective()
    bounds = bounds or AutonomyBounds()
    if not supplied or len(supplied) > bounds.max_candidates:
        raise BoundedAutonomyError("candidate count exceeds autonomy bounds")
    if not isinstance(proposal_round, int) or not 0 <= proposal_round <= bounds.max_proposal_round:
        raise BoundedAutonomyError("proposal round exceeds autonomy bounds")
    if not isinstance(evidence_digest, str) or len(evidence_digest) != 64:
        raise BoundedAutonomyError("autonomy proposal requires a 64-character evidence digest")
    decision = select_survival_branch(supplied, objective=objective)
    candidates = tuple(sorted(branch.branch_digest for branch in supplied))
    result = BoundedAutonomyProposal(
        decision=decision,
        candidate_branch_digests=candidates,
        objective_digest=objective.digest,
        bounds_digest=bounds.digest,
        proposal_round=proposal_round,
        evidence_digest=evidence_digest,
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _proposal_digest(
            decision_digest=decision.digest,
            candidates=candidates,
            objective_digest=objective.digest,
            bounds_digest=bounds.digest,
            proposal_round=proposal_round,
            evidence_digest=evidence_digest,
        ),
    )
    result.assert_sealed(branches=supplied, objective=objective, bounds=bounds)
    return result
