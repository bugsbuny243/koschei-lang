from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_execution_gate_v1 import GalaxyExecutionError, enforce_galaxy_critical_effect
from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_failure_independence_v1 import (
    AxisFailureRootAttestation,
    KharFailureIndependenceError,
    seal_failure_independent_sathra,
)
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
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
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
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
    veyra = birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
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
    return mir, proof, veyra, aevra, request, bound, sathra, sathra_binding, independence


def test_complete_galaxy_gate_executes_one_living_independent_event_once():
    values = build()
    mir, proof, veyra, aevra, request, bound, sathra, sb, independence = values
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black_hole, AtomicExecutionCoordinator(
            Path(directory) / "execution.sqlite3"
        ) as coordinator:
            coordinator.initialize(state)
            decision, value, claim = enforce_galaxy_critical_effect(
                black_hole=black_hole,
                coordinator=coordinator,
                mir=mir,
                veyra=veyra,
                aevra=aevra,
                request=request,
                proof=proof,
                request_bound_proof=bound,
                sathra=sathra,
                sathra_binding=sb,
                failure_independence=independence,
                effect=lambda item: calls.append(item.digest) or "done",
            )
            assert decision.decision == "ALLOW"
            assert value == "done"
            assert claim.state == "COMMITTED"
            assert calls == [request.digest]
            with pytest.raises(AtomicExecutionCoordinatorError):
                enforce_galaxy_critical_effect(
                    black_hole=black_hole,
                    coordinator=coordinator,
                    mir=mir,
                    veyra=veyra,
                    aevra=aevra,
                    request=request,
                    proof=proof,
                    request_bound_proof=bound,
                    sathra=sathra,
                    sathra_binding=sb,
                    failure_independence=independence,
                    effect=lambda _: "must-not-run",
                )


def test_morth_blocks_complete_six_axis_independent_event():
    mir, proof, veyra, aevra, request, bound, sathra, sb, independence = build()
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black_hole, AtomicExecutionCoordinator(
            Path(directory) / "execution.sqlite3"
        ) as coordinator:
            coordinator.initialize(state)
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
                    black_hole=black_hole,
                    coordinator=coordinator,
                    mir=mir,
                    veyra=veyra,
                    aevra=aevra,
                    request=request,
                    proof=proof,
                    request_bound_proof=bound,
                    sathra=sathra,
                    sathra_binding=sb,
                    failure_independence=independence,
                    effect=lambda _: "must-not-run",
                )


def test_independence_proof_for_foreign_sathra_is_rejected_before_execution():
    mir, proof, veyra, aevra, request, bound, sathra, sb, independence = build()
    forged = replace(independence, sathra_digest=d("foreign"))
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black_hole, AtomicExecutionCoordinator(
            Path(directory) / "execution.sqlite3"
        ) as coordinator:
            coordinator.initialize(state)
            with pytest.raises(GalaxyExecutionError):
                enforce_galaxy_critical_effect(
                    black_hole=black_hole,
                    coordinator=coordinator,
                    mir=mir,
                    veyra=veyra,
                    aevra=aevra,
                    request=request,
                    proof=proof,
                    request_bound_proof=bound,
                    sathra=sathra,
                    sathra_binding=sb,
                    failure_independence=forged,
                    effect=lambda _: "must-not-run",
                )
