from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_execution_gate_v1 import GalaxyExecutionError, enforce_galaxy_critical_effect
from koschei.galaxy_identity_v1 import birth_aevra
from koschei.khar_constitution_v1 import birth_canonical_veyra
from koschei.khar_failure_independence_v1 import (
    AxisFailureRootAttestation,
    seal_failure_independent_sathra,
)
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from koschei.morth_black_hole_v1 import DurableBlackHole
from koschei.native_sigil_atomic_execution_coordinator_v1 import (
    AtomicExecutionCoordinator,
    AtomicExecutionCoordinatorError,
)
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import bind_sathra_to_request
from koschei.universe_state_machine_v1 import initial_universe_state


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def build():
    mir = lower_native_sigils(
        parse("ka withdrawal; vor withdrawal; shi withdrawal; thal withdrawal; nur withdrawal;")
    )
    plan = expand_native_sigil_mir(mir).library_plan
    proof = seal_native_sigil_proof(
        mir,
        [
            make_receipt(
                activation_step_id=step.activation_step_id,
                obligation=step.obligation,
                subsystem=step.subsystem,
                proof_kind=step.proof_kind,
                evidence_digest=d(step.binding_digest),
                success=True,
            )
            for step in plan.steps
        ],
    )
    veyra = birth_canonical_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=d("birth"),
        birth_epoch=7,
    )
    matrix = birth_matrix(
        veyra,
        instance_digest=d("matrix-a"),
        reality_commitment_digest=d("matrix-reality-a"),
        birth_epoch=7,
    )
    hara = birth_hara(
        matrix,
        veyra,
        aevra,
        mir,
        horizon_commitment_digest=d("hara-a"),
        epoch=7,
    )
    matrix_admission = admit_matrix_hara(
        matrix,
        hara,
        veyra,
        aevra,
        mir,
        evidence_digest=d("matrix-admission"),
    )
    request = seal_effect_request(
        mir,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d("payload"),
        identity_digest=d("identity"),
        epoch=7,
        nonce_digest=d("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    sathra = seal_sathra(
        AxisWitness(
            axis=axis,
            aevra_digest=aevra.digest,
            veyra_digest=veyra.digest,
            event_digest=request.digest,
            reality_digest=mir.fingerprint,
            epoch=7,
            witness_digest=d("witness-" + axis),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )
    sathra_binding = bind_sathra_to_request(mir, veyra, aevra, request, sathra)
    witnesses = dict(sathra.axis_witnesses)
    independence = seal_failure_independent_sathra(
        sathra,
        (
            AxisFailureRootAttestation(
                axis=axis,
                axis_witness_digest=witnesses[axis],
                failure_root_digest=d("root-" + axis),
                attestation_domain_digest=d("attestor-" + axis),
                evidence_digest=d("independence-" + axis),
            )
            for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
        ),
    )
    return (
        mir,
        proof,
        veyra,
        aevra,
        matrix,
        hara,
        matrix_admission,
        request,
        bound,
        sathra,
        sathra_binding,
        independence,
    )


def kwargs(values, black_hole, matrix_horizon, coordinator, effect):
    mir, proof, veyra, aevra, matrix, hara, matrix_admission, request, bound, sathra, sb, independence = values
    return dict(
        black_hole=black_hole,
        matrix_horizon=matrix_horizon,
        coordinator=coordinator,
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        matrix_admission=matrix_admission,
        request=request,
        proof=proof,
        request_bound_proof=bound,
        sathra=sathra,
        sathra_binding=sb,
        failure_independence=independence,
        effect=effect,
    )


def open_world(directory, values):
    black_hole = DurableBlackHole(Path(directory) / "black-hole.sqlite3")
    horizon = DurableMatrixHorizonFence(Path(directory) / "matrix-horizon.sqlite3")
    coordinator = AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3")
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    coordinator.initialize(state)
    horizon.initialize(values[6])
    return black_hole, horizon, coordinator


def close_world(black_hole, horizon, coordinator):
    black_hole.close()
    horizon.close()
    coordinator.close()


def test_complete_galaxy_gate_executes_one_living_independent_current_hara_event_once():
    values = build()
    request = values[7]
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, values)
        try:
            decision, value, claim = enforce_galaxy_critical_effect(
                **kwargs(values, black_hole, horizon, coordinator, lambda item: calls.append(item.digest) or "done")
            )
            assert decision.decision == "ALLOW"
            assert value == "done"
            assert claim.state == "COMMITTED"
            assert calls == [request.digest]
            with pytest.raises(AtomicExecutionCoordinatorError):
                enforce_galaxy_critical_effect(
                    **kwargs(values, black_hole, horizon, coordinator, lambda _: "must-not-run")
                )
        finally:
            close_world(black_hole, horizon, coordinator)


def test_morth_blocks_complete_current_hara_event():
    values = build()
    mir, _, veyra, aevra = values[:4]
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, values)
        try:
            black_hole.enter_event_horizon(
                aevra,
                veyra,
                mir,
                death_epoch=7,
                cause_digest=d("cause"),
                evidence_digest=d("death-evidence"),
            )
            with pytest.raises(GalaxyExecutionError, match="no living future"):
                enforce_galaxy_critical_effect(
                    **kwargs(values, black_hole, horizon, coordinator, lambda _: "must-not-run")
                )
        finally:
            close_world(black_hole, horizon, coordinator)


def test_foreign_failure_independence_is_rejected_before_execution():
    values = list(build())
    values[11] = replace(values[11], sathra_digest=d("foreign"))
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, tuple(values))
        try:
            with pytest.raises(GalaxyExecutionError):
                enforce_galaxy_critical_effect(
                    **kwargs(tuple(values), black_hole, horizon, coordinator, lambda _: "must-not-run")
                )
        finally:
            close_world(black_hole, horizon, coordinator)


def test_foreign_matrix_admission_is_rejected_before_execution():
    values = list(build())
    original_admission = values[6]
    values[6] = replace(original_admission, hara_digest=d("foreign-hara"))
    with tempfile.TemporaryDirectory() as directory:
        black_hole = DurableBlackHole(Path(directory) / "black-hole.sqlite3")
        horizon = DurableMatrixHorizonFence(Path(directory) / "matrix-horizon.sqlite3")
        coordinator = AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3")
        try:
            coordinator.initialize(
                initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
            )
            horizon.initialize(original_admission)
            with pytest.raises(GalaxyExecutionError):
                enforce_galaxy_critical_effect(
                    **kwargs(tuple(values), black_hole, horizon, coordinator, lambda _: "must-not-run")
                )
        finally:
            close_world(black_hole, horizon, coordinator)


def test_non_current_hara_is_rejected_before_effect():
    values = build()
    stale_admission = values[6]
    with tempfile.TemporaryDirectory() as directory:
        black_hole, horizon, coordinator = open_world(directory, values)
        try:
            mir, _, veyra, aevra = values[:4]
            next_matrix = birth_matrix(
                veyra,
                instance_digest=d("matrix-b"),
                reality_commitment_digest=d("matrix-reality-b"),
                birth_epoch=8,
            )
            next_hara = birth_hara(
                next_matrix,
                veyra,
                aevra,
                mir,
                horizon_commitment_digest=d("hara-b"),
                epoch=8,
            )
            next_admission = admit_matrix_hara(
                next_matrix,
                next_hara,
                veyra,
                aevra,
                mir,
                evidence_digest=d("matrix-admission-b"),
            )
            horizon.advance(stale_admission, next_admission, cause_digest=d("matrix-move"))
            calls = []
            with pytest.raises(GalaxyExecutionError):
                enforce_galaxy_critical_effect(
                    **kwargs(values, black_hole, horizon, coordinator, lambda _: calls.append(1))
                )
            assert calls == []
        finally:
            close_world(black_hole, horizon, coordinator)
