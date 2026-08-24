from dataclasses import replace
import hashlib

import pytest

import koschei.bounded_autonomy_execution_v1 as gate
from koschei.bounded_autonomy_v1 import AutonomyBounds, propose_bounded_survival
from koschei.survival_branch_v1 import SurvivalBranch, SurvivalObjective


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def branch(name: str, availability: int = 0) -> SurvivalBranch:
    return SurvivalBranch(
        branch_digest=d("branch:" + name),
        action_commitment_digest=d("action:" + name),
        khar_preserved=True,
        authority_escape=0,
        cross_domain_spread=0,
        evidence_loss=0,
        irreversible_loss=0,
        availability_loss=availability,
        recoverability=1000,
    )


def kwargs(proposal, branches, selected, objective, bounds):
    return dict(
        proposal=proposal,
        branches=branches,
        objective=objective,
        bounds=bounds,
        branch=selected,
        survival_binding=None,
        black_hole=None,
        matrix_horizon=None,
        coordinator=None,
        mir=None,
        veyra=None,
        aevra=None,
        matrix=None,
        hara=None,
        matrix_admission=None,
        request=None,
        proof=None,
        request_bound_proof=None,
        sathra=None,
        sathra_binding=None,
        failure_independence=None,
        effect=lambda _: "unused",
    )


def test_autonomy_wrapper_delegates_only_chosen_branch_to_survival_gate(monkeypatch):
    chosen = branch("chosen", availability=0)
    other = branch("other", availability=100)
    branches = (chosen, other)
    objective = SurvivalObjective()
    bounds = AutonomyBounds()
    proposal = propose_bounded_survival(
        branches, objective=objective, bounds=bounds,
        proposal_round=1, evidence_digest=d("evidence"),
    )
    calls = []

    def fake_survival_gate(**items):
        calls.append(items)
        return "decision", "value", "claim"

    monkeypatch.setattr(gate, "enforce_survival_branch_effect", fake_survival_gate)
    result = gate.enforce_bounded_autonomy_effect(
        **kwargs(proposal, branches, chosen, objective, bounds)
    )
    assert result == ("decision", "value", "claim")
    assert len(calls) == 1
    assert calls[0]["decision"] == proposal.decision
    assert calls[0]["branch"] == chosen


def test_autonomy_wrapper_rejects_non_chosen_branch_before_survival_gate(monkeypatch):
    chosen = branch("chosen", availability=0)
    other = branch("other", availability=100)
    branches = (chosen, other)
    objective = SurvivalObjective()
    bounds = AutonomyBounds()
    proposal = propose_bounded_survival(
        branches, objective=objective, bounds=bounds,
        proposal_round=1, evidence_digest=d("evidence"),
    )
    calls = []
    monkeypatch.setattr(gate, "enforce_survival_branch_effect", lambda **_: calls.append(1))
    with pytest.raises(gate.BoundedAutonomyExecutionError, match="not the proposal's chosen branch"):
        gate.enforce_bounded_autonomy_effect(
            **kwargs(proposal, branches, other, objective, bounds)
        )
    assert calls == []


def test_tampered_authority_proposal_is_rejected_before_survival_gate(monkeypatch):
    chosen = branch("chosen")
    branches = (chosen,)
    objective = SurvivalObjective()
    bounds = AutonomyBounds()
    proposal = propose_bounded_survival(
        branches, objective=objective, bounds=bounds,
        proposal_round=1, evidence_digest=d("evidence"),
    )
    forged = replace(proposal, authority=True)
    calls = []
    monkeypatch.setattr(gate, "enforce_survival_branch_effect", lambda **_: calls.append(1))
    with pytest.raises(gate.BoundedAutonomyExecutionError):
        gate.enforce_bounded_autonomy_effect(
            **kwargs(forged, branches, chosen, objective, bounds)
        )
    assert calls == []
