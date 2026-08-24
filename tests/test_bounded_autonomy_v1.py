from dataclasses import replace
import hashlib

import pytest

from koschei.bounded_autonomy_v1 import (
    AutonomyBounds,
    BoundedAutonomyError,
    propose_bounded_survival,
)
from koschei.survival_branch_v1 import SurvivalBranch, SurvivalObjective


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def branch(name: str, *, khar=True, authority=0, spread=0, availability=0):
    return SurvivalBranch(
        branch_digest=d("branch:" + name),
        action_commitment_digest=d("action:" + name),
        khar_preserved=khar,
        authority_escape=authority,
        cross_domain_spread=spread,
        evidence_loss=0,
        irreversible_loss=0,
        availability_loss=availability,
        recoverability=1000,
    )


def test_autonomy_can_only_propose_selector_chosen_safe_branch():
    safe = branch("safe", availability=10)
    unsafe = branch("unsafe", khar=False, availability=0)
    proposal = propose_bounded_survival(
        (unsafe, safe), proposal_round=1, evidence_digest=d("evidence")
    )
    assert proposal.decision.chosen_branch_digest == safe.branch_digest
    assert not proposal.authority


def test_autonomy_cannot_choose_authority_escape_even_when_it_is_cheapest():
    escape = branch("escape", authority=1, availability=0)
    contained = branch("contained", availability=900)
    proposal = propose_bounded_survival(
        (escape, contained), proposal_round=2, evidence_digest=d("evidence")
    )
    assert proposal.decision.chosen_branch_digest == contained.branch_digest


def test_autonomy_candidate_count_is_bounded():
    bounds = AutonomyBounds(max_candidates=2)
    with pytest.raises(BoundedAutonomyError, match="candidate count"):
        propose_bounded_survival(
            (branch("a"), branch("b"), branch("c")),
            bounds=bounds,
            proposal_round=1,
            evidence_digest=d("evidence"),
        )


def test_autonomy_cannot_rewrite_objective_after_proposal():
    branches = (branch("a", availability=10), branch("b", availability=20))
    original = SurvivalObjective(availability_loss_weight=1)
    proposal = propose_bounded_survival(
        branches, objective=original, proposal_round=3, evidence_digest=d("evidence")
    )
    changed = SurvivalObjective(availability_loss_weight=100)
    with pytest.raises(BoundedAutonomyError, match="objective mismatch"):
        proposal.assert_sealed(branches=branches, objective=changed, bounds=AutonomyBounds())


def test_autonomy_proposal_cannot_be_promoted_to_authority_by_tampering():
    branches = (branch("a"),)
    proposal = propose_bounded_survival(
        branches, proposal_round=1, evidence_digest=d("evidence")
    )
    forged = replace(proposal, authority=True)
    with pytest.raises(BoundedAutonomyError, match="cannot carry authority"):
        forged.assert_sealed(branches=branches, objective=SurvivalObjective(), bounds=AutonomyBounds())


def test_autonomy_cannot_smuggle_a_different_decision():
    branches = (branch("a", availability=10), branch("b", availability=20))
    proposal = propose_bounded_survival(
        branches, proposal_round=1, evidence_digest=d("evidence")
    )
    other = propose_bounded_survival(
        (branch("c"),), proposal_round=1, evidence_digest=d("other")
    )
    forged = replace(proposal, decision=other.decision)
    with pytest.raises(BoundedAutonomyError):
        forged.assert_sealed(branches=branches, objective=SurvivalObjective(), bounds=AutonomyBounds())
