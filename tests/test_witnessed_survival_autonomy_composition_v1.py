from types import SimpleNamespace

import koschei.bounded_autonomy_execution_v1 as autonomy_gate
import koschei.survival_execution_gate_v1 as survival_gate


def test_witnessed_survival_routes_only_to_witnessed_galaxy_gate(monkeypatch):
    implementation_root = object()
    observed = {}

    monkeypatch.setattr(
        survival_gate,
        "_require_exact_survival_binding",
        lambda **kwargs: observed.setdefault("binding", kwargs),
    )

    def witnessed_delegate(**kwargs):
        observed["witnessed"] = kwargs
        return ("decision", "result", "claim")

    monkeypatch.setattr(
        survival_gate,
        "enforce_witnessed_galaxy_critical_effect",
        witnessed_delegate,
    )
    monkeypatch.setattr(
        survival_gate,
        "enforce_galaxy_critical_effect",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("witnessed survival must not use the base Galaxy gate")
        ),
    )

    result = survival_gate.enforce_witnessed_survival_branch_effect(
        implementation_root=implementation_root,
        decision=object(),
        branch=object(),
        survival_binding=object(),
        black_hole=object(),
        matrix_horizon=object(),
        coordinator=object(),
        mir=object(),
        veyra=object(),
        aevra=object(),
        matrix=object(),
        hara=object(),
        matrix_admission=object(),
        request=object(),
        proof=object(),
        request_bound_proof=object(),
        sathra=object(),
        sathra_binding=object(),
        failure_independence=object(),
        effect=lambda request: request,
    )

    assert result == ("decision", "result", "claim")
    assert "binding" in observed
    assert observed["witnessed"]["implementation_root"] is implementation_root


def test_witnessed_autonomy_routes_only_to_witnessed_survival_gate(monkeypatch):
    implementation_root = object()
    proposal = SimpleNamespace(decision=object())
    observed = {}

    monkeypatch.setattr(
        autonomy_gate,
        "_require_exact_autonomy_proposal",
        lambda **kwargs: observed.setdefault("proposal", kwargs),
    )

    def witnessed_delegate(**kwargs):
        observed["witnessed"] = kwargs
        return ("decision", "result", "claim")

    monkeypatch.setattr(
        autonomy_gate,
        "enforce_witnessed_survival_branch_effect",
        witnessed_delegate,
    )
    monkeypatch.setattr(
        autonomy_gate,
        "enforce_survival_branch_effect",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("witnessed autonomy must not use the base survival gate")
        ),
    )

    result = autonomy_gate.enforce_witnessed_bounded_autonomy_effect(
        implementation_root=implementation_root,
        proposal=proposal,
        branches=(object(),),
        objective=object(),
        bounds=object(),
        branch=object(),
        survival_binding=object(),
        black_hole=object(),
        matrix_horizon=object(),
        coordinator=object(),
        mir=object(),
        veyra=object(),
        aevra=object(),
        matrix=object(),
        hara=object(),
        matrix_admission=object(),
        request=object(),
        proof=object(),
        request_bound_proof=object(),
        sathra=object(),
        sathra_binding=object(),
        failure_independence=object(),
        effect=lambda request: request,
    )

    assert result == ("decision", "result", "claim")
    assert "proposal" in observed
    assert observed["witnessed"]["implementation_root"] is implementation_root
    assert observed["witnessed"]["decision"] is proposal.decision
