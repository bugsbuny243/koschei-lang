from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_identity_v1 import birth_aevra
from koschei.khar_constitution_v1 import birth_canonical_veyra
from koschei.khar_failure_independence_v1 import AxisFailureRootAttestation, seal_failure_independent_sathra
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from koschei.morth_black_hole_v1 import DurableBlackHole
from koschei.native_sigil_atomic_execution_coordinator_v1 import AtomicExecutionCoordinator, AtomicExecutionCoordinatorError
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import bind_sathra_to_request
from koschei.survival_branch_v1 import SurvivalBranch, select_survival_branch
from koschei.survival_event_binding_v1 import bind_survival_decision_to_event, survival_action_commitment
from koschei.survival_execution_gate_v1 import SurvivalExecutionError, enforce_survival_branch_effect
from koschei.universe_state_machine_v1 import initial_universe_state


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def build():
    mir = lower_native_sigils(parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;"))
    plan = expand_native_sigil_mir(mir).library_plan
    proof = seal_native_sigil_proof(
        mir,
        [make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=d(step.binding_digest),
            success=True,
        ) for step in plan.steps],
    )
    veyra = birth_canonical_veyra(
        profile_digest=d("bank-profile"), genesis_digest=d("genesis"),
        instance_digest=d("bank-a"), birth_epoch=7,
    )
    aevra = birth_aevra(
        veyra, mir, sigil="vor", subject="withdrawal",
        birth_evidence_digest=d("birth"), birth_epoch=7,
    )
    matrix = birth_matrix(
        veyra, instance_digest=d("matrix-a"),
        reality_commitment_digest=d("matrix-reality"), birth_epoch=7,
    )
    hara = birth_hara(
        matrix, veyra, aevra, mir,
        horizon_commitment_digest=d("hara-a"), epoch=7,
    )
    admission = admit_matrix_hara(
        matrix, hara, veyra, aevra, mir, evidence_digest=d("matrix-admission")
    )
    request = seal_effect_request(
        mir, effect_id="withdrawal-42", subject="withdrawal", operation="signer.execute",
        request_digest=d("payload"), identity_digest=d("identity"), epoch=7, nonce_digest=d("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    sathra = seal_sathra(
        AxisWitness(
            axis=axis, aevra_digest=aevra.digest, veyra_digest=veyra.digest,
            event_digest=request.digest, reality_digest=mir.fingerprint, epoch=7,
            witness_digest=d("witness-" + axis),
        ) for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )
    sb = bind_sathra_to_request(mir, veyra, aevra, request, sathra)
    witness_map = dict(sathra.axis_witnesses)
    independence = seal_failure_independent_sathra(
        sathra,
        tuple(AxisFailureRootAttestation(
            axis=axis,
            axis_witness_digest=witness_map[axis],
            failure_root_digest=d("root-" + axis),
            attestation_domain_digest=d("attestor-" + axis),
            evidence_digest=d("evidence-" + axis),
        ) for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")),
    )
    action = survival_action_commitment(
        mir=mir, veyra=veyra, aevra=aevra, matrix=matrix, hara=hara, request=request
    )
    branch = SurvivalBranch(
        branch_digest=d("survival-branch"), action_commitment_digest=action,
        khar_preserved=True, authority_escape=0, cross_domain_spread=0,
        evidence_loss=0, irreversible_loss=20, availability_loss=40, recoverability=900,
    )
    decision = select_survival_branch((branch,))
    survival_binding = bind_survival_decision_to_event(
        decision=decision, branch=branch, mir=mir, veyra=veyra, aevra=aevra,
        matrix=matrix, hara=hara, matrix_admission=admission, request=request,
        sathra=sathra, sathra_binding=sb,
    )
    return (
        mir, proof, veyra, aevra, matrix, hara, admission, request, bound,
        sathra, sb, independence, branch, decision, survival_binding,
    )


def open_world(directory, values):
    black_hole = DurableBlackHole(Path(directory) / "black-hole.sqlite3")
    horizon = DurableMatrixHorizonFence(Path(directory) / "matrix-horizon.sqlite3")
    coordinator = AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3")
    coordinator.initialize(initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7))
    horizon.initialize(values[6])
    return black_hole, horizon, coordinator


def args(values, black_hole, horizon, coordinator, effect):
    mir, proof, veyra, aevra, matrix, hara, admission, request, bound, sathra, sb, independence, branch, decision, survival_binding = values
    return dict(
        decision=decision, branch=branch, survival_binding=survival_binding,
        black_hole=black_hole, matrix_horizon=horizon, coordinator=coordinator,
        mir=mir, veyra=veyra, aevra=aevra, matrix=matrix, hara=hara,
        matrix_admission=admission, request=request, proof=proof,
        request_bound_proof=bound, sathra=sathra, sathra_binding=sb,
        failure_independence=independence, effect=effect,
    )


def test_survival_plan_still_requires_full_galaxy_gate_and_executes_once():
    values = build()
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, values)
        try:
            decision, value, claim = enforce_survival_branch_effect(
                **args(values, black_hole, horizon, coordinator, lambda item: calls.append(item.digest) or "survived")
            )
            assert decision.decision == "ALLOW"
            assert value == "survived"
            assert claim.state == "COMMITTED"
            assert calls == [values[7].digest]
            with pytest.raises(AtomicExecutionCoordinatorError):
                enforce_survival_branch_effect(
                    **args(values, black_hole, horizon, coordinator, lambda _: "must-not-run")
                )
        finally:
            black_hole.close(); horizon.close(); coordinator.close()


def test_tampered_survival_binding_cannot_reach_effect():
    values = list(build())
    values[14] = replace(values[14], hara_digest=d("foreign-hara"))
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, tuple(values))
        try:
            with pytest.raises(SurvivalExecutionError):
                enforce_survival_branch_effect(
                    **args(tuple(values), black_hole, horizon, coordinator, lambda _: calls.append(1))
                )
            assert calls == []
        finally:
            black_hole.close(); horizon.close(); coordinator.close()


def test_survival_plan_cannot_bypass_morth():
    values = build()
    mir, _, veyra, aevra = values[:4]
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, values)
        try:
            black_hole.enter_event_horizon(
                aevra, veyra, mir, death_epoch=7,
                cause_digest=d("morth-cause"), evidence_digest=d("morth-evidence"),
            )
            with pytest.raises(ValueError):
                enforce_survival_branch_effect(
                    **args(values, black_hole, horizon, coordinator, lambda _: calls.append(1))
                )
            assert calls == []
        finally:
            black_hole.close(); horizon.close(); coordinator.close()
