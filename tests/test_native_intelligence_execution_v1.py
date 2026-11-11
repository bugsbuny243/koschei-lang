import hashlib
from types import SimpleNamespace

import pytest

import koschei.native_intelligence_execution_v1 as gate
from koschei.native_intelligence_v1 import (
    bind_native_intelligence_event,
    build_native_intelligence_identity,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def model_identity():
    return build_native_intelligence_identity(
        base_model_revision="a" * 40,
        base_weights_digest=d("weights"),
        curriculum_digest=d("curriculum"),
        adapter_digest=d("adapter"),
        training_run_digest=d("run"),
        source_commit="b" * 40,
        training_method="lora-sft",
    )


class Proposal:
    def __init__(self, digest: str):
        self.digest = digest

    def assert_sealed(self, *, branches, objective, bounds):
        return None


def test_model_originated_action_routes_only_to_witnessed_autonomy(monkeypatch):
    model = model_identity()
    proposal = Proposal(d("proposal"))
    veyra = SimpleNamespace(digest=d("veyra"))
    mir = SimpleNamespace(fingerprint=d("mir"))
    request = SimpleNamespace(epoch=3)
    binding = bind_native_intelligence_event(
        model,
        veyra_digest=veyra.digest,
        native_mir_fingerprint=mir.fingerprint,
        epoch=request.epoch,
        proposal_digest=proposal.digest,
        observation_digest=d("observation"),
        output_digest=d("output"),
    )
    observed = {}

    def delegate(**kwargs):
        observed.update(kwargs)
        return ("decision", "result", "claim")

    monkeypatch.setattr(gate, "enforce_witnessed_bounded_autonomy_effect", delegate)

    result = gate.enforce_native_intelligence_effect(
        intelligence=model,
        intelligence_binding=binding,
        implementation_measurement=object(),
        implementation_witnesses=(object(), object()),
        implementation_witness_keys={"a": b"A" * 32, "b": b"B" * 32},
        proposal=proposal,
        branches=(object(),),
        objective=object(),
        bounds=object(),
        branch=object(),
        survival_binding=object(),
        black_hole=object(),
        matrix_horizon=object(),
        coordinator=object(),
        mir=mir,
        veyra=veyra,
        aevra=object(),
        matrix=object(),
        hara=object(),
        matrix_admission=object(),
        request=request,
        proof=object(),
        request_bound_proof=object(),
        sathra=object(),
        sathra_binding=object(),
        failure_independence=object(),
        effect=lambda req: req,
    )

    assert result == ("decision", "result", "claim")
    assert observed["proposal"] is proposal
    assert observed["implementation_witnesses"]


def test_model_output_bound_to_other_epoch_is_rejected_before_execution(monkeypatch):
    model = model_identity()
    proposal = Proposal(d("proposal"))
    veyra = SimpleNamespace(digest=d("veyra"))
    mir = SimpleNamespace(fingerprint=d("mir"))
    binding = bind_native_intelligence_event(
        model,
        veyra_digest=veyra.digest,
        native_mir_fingerprint=mir.fingerprint,
        epoch=2,
        proposal_digest=proposal.digest,
        observation_digest=d("observation"),
        output_digest=d("output"),
    )
    called = False

    def delegate(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("witnessed autonomy must not be reached")

    monkeypatch.setattr(gate, "enforce_witnessed_bounded_autonomy_effect", delegate)

    with pytest.raises(gate.NativeIntelligenceExecutionError, match="epoch mismatch"):
        gate.enforce_native_intelligence_effect(
            intelligence=model,
            intelligence_binding=binding,
            implementation_measurement=object(),
            implementation_witnesses=(object(), object()),
            implementation_witness_keys={},
            proposal=proposal,
            branches=(object(),),
            objective=object(),
            bounds=object(),
            branch=object(),
            survival_binding=object(),
            black_hole=object(),
            matrix_horizon=object(),
            coordinator=object(),
            mir=mir,
            veyra=veyra,
            aevra=object(),
            matrix=object(),
            hara=object(),
            matrix_admission=object(),
            request=SimpleNamespace(epoch=3),
            proof=object(),
            request_bound_proof=object(),
            sathra=object(),
            sathra_binding=object(),
            failure_independence=object(),
            effect=lambda req: req,
        )
    assert called is False
