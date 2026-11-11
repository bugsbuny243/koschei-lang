from dataclasses import replace
import hashlib

import pytest

from koschei.survival_branch_v1 import (
    SurvivalBranch,
    SurvivalBranchError,
    SurvivalObjective,
    select_survival_branch,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def branch(
    name: str,
    *,
    khar=True,
    authority=0,
    spread=0,
    evidence=0,
    irreversible=0,
    availability=0,
    recoverability=1000,
):
    return SurvivalBranch(
        branch_digest=d("branch:" + name),
        action_commitment_digest=d("action:" + name),
        khar_preserved=khar,
        authority_escape=authority,
        cross_domain_spread=spread,
        evidence_loss=evidence,
        irreversible_loss=irreversible,
        availability_loss=availability,
        recoverability=recoverability,
    )


def test_branch_that_weakens_khar_is_impossible_even_if_availability_is_perfect():
    unsafe = branch("unsafe", khar=False, availability=0, irreversible=0)
    safe = branch("safe", availability=500, irreversible=100)
    decision = select_survival_branch((unsafe, safe))
    assert decision.chosen_branch_digest == safe.branch_digest
    assert unsafe.branch_digest in decision.rejected_branch_digests


def test_default_objective_rejects_any_authority_escape():
    escape = branch("escape", authority=1, availability=0)
    sacrifice = branch("sacrifice", authority=0, availability=900, irreversible=400)
    decision = select_survival_branch((escape, sacrifice))
    assert decision.chosen_branch_digest == sacrifice.branch_digest


def test_default_objective_rejects_cross_domain_spread():
    spreading = branch("spread", spread=1)
    contained = branch("contained", availability=800, irreversible=250)
    decision = select_survival_branch((spreading, contained))
    assert decision.chosen_branch_digest == contained.branch_digest


def test_least_total_loss_is_deterministic_among_safe_branches():
    preserve = branch("preserve", irreversible=50, availability=400, evidence=0, recoverability=900)
    destroy = branch("destroy", irreversible=500, availability=100, evidence=0, recoverability=1000)
    decision_a = select_survival_branch((destroy, preserve))
    decision_b = select_survival_branch((preserve, destroy))
    assert decision_a == decision_b
    assert decision_a.chosen_branch_digest == preserve.branch_digest


def test_evidence_loss_is_more_expensive_than_availability_by_default():
    evidence_loss = branch("lose-evidence", evidence=80, availability=0)
    availability_loss = branch("lose-availability", evidence=0, availability=600)
    decision = select_survival_branch((evidence_loss, availability_loss))
    assert decision.chosen_branch_digest == availability_loss.branch_digest


def test_no_safe_future_fails_closed_instead_of_choosing_best_bad_branch():
    with pytest.raises(SurvivalBranchError, match="no branch preserves Khar"):
        select_survival_branch(
            (
                branch("escape", authority=5),
                branch("spread", spread=10),
                branch("khar-break", khar=False),
            )
        )


def test_policy_can_tighten_evidence_ceiling():
    objective = SurvivalObjective(max_evidence_loss=0)
    with pytest.raises(SurvivalBranchError):
        select_survival_branch((branch("evidence-loss", evidence=1),), objective=objective)


def test_tampered_decision_fails_closed():
    decision = select_survival_branch((branch("a"), branch("b", availability=1)))
    forged = replace(decision, chosen_score=decision.chosen_score + 1)
    with pytest.raises(SurvivalBranchError, match="seal mismatch"):
        forged.assert_sealed()
