from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.canonical_materialization_handle_v1 import (
    CanonicalMaterializationEffectGateV1,
    CanonicalMaterializationHandleV1Error,
    CanonicalMaterializationRegistryV1,
    GalaxyMaterializationContextV1,
)
from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.galaxy_execution_gate_v1 import GalaxyExecutionError
from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_constitution_v1 import birth_canonical_veyra
from koschei.khar_failure_independence_v1 import (
    AxisFailureRootAttestation,
    seal_failure_independent_sathra,
)
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0,
    derive_adaptive_visibility_v0,
)
from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0,
    VisibilityPosture,
)
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from koschei.morth_black_hole_v1 import DurableBlackHole
from koschei.native_sigil_atomic_execution_coordinator_v1 import AtomicExecutionCoordinator
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import (
    bind_proof_to_request,
    seal_effect_request,
)
from koschei.parser import parse
from koschei.representation_boundary_v1 import (
    issue_observable_representation_v1,
    mint_reconstruction_grant_v1,
)
from koschei.representation_reconstruction_gate_v1 import (
    ReconstructionConsumptionLedgerV1,
    RepresentationReconstructionGateV1,
)
from koschei.sathra_request_binding_v1 import bind_sathra_to_request
from koschei.universe_state_machine_v1 import initial_universe_state

SOURCE = "ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;"
AXES = ("khor", "sei", "rha", "vaal", "teyr", "esh")
VEIL = b"v" * 32
RECON = b"r" * 32
RECEIPT = b"c" * 32
MATERIALIZE = b"m" * 32


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def request_for(mir, epoch, tag="42"):
    return seal_effect_request(
        mir,
        effect_id="withdrawal:" + tag,
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d("payload-" + tag),
        identity_digest=d("identity-" + tag),
        epoch=epoch,
        nonce_digest=d("nonce-" + tag),
    )


def proof_for(mir, plan, failed_obligation=None):
    return seal_native_sigil_proof(
        mir,
        tuple(
            make_receipt(
                activation_step_id=step.activation_step_id,
                obligation=step.obligation,
                subsystem=step.subsystem,
                proof_kind=step.proof_kind,
                evidence_digest=d(step.binding_digest),
                success=step.obligation != failed_obligation,
            )
            for step in plan.library_plan.steps
        ),
    )


def build_world(directory, *, backing=None, canonical_khar=True):
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir)
    proof = proof_for(mir, plan)
    if canonical_khar:
        veyra = birth_canonical_veyra(
            profile_digest=d("profile"),
            genesis_digest=d("genesis"),
            instance_digest=d("instance"),
            birth_epoch=7,
        )
    else:
        veyra = birth_veyra(
            profile_digest=d("profile"),
            genesis_digest=d("genesis"),
            constitution_digest=d("substituted-khar"),
            instance_digest=d("instance"),
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
    request = request_for(mir, 7)
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
        for axis in AXES
    )
    sathra_binding = bind_sathra_to_request(mir, veyra, aevra, request, sathra)
    witness_map = dict(sathra.axis_witnesses)
    independence = seal_failure_independent_sathra(
        sathra,
        tuple(
            AxisFailureRootAttestation(
                axis=axis,
                axis_witness_digest=witness_map[axis],
                failure_root_digest=d("root-" + axis),
                attestation_domain_digest=d("attestor-" + axis),
                evidence_digest=d("independence-" + axis),
            )
            for axis in AXES
        ),
    )

    decision = LearningResistanceDecisionV0(
        "observer", d32("session"), 1, 10, 3, 2, 0, 1, 300,
        VisibilityPosture.NORMAL, 3, d32("decision"), True, False,
    )
    envelope = derive_adaptive_visibility_v0(
        decision=decision,
        policy=VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False),
        current_tick=70,
        rotation_secret_commitment=d32("rotation-secret"),
    )
    assert envelope.visibility_epoch == 7
    representation = issue_observable_representation_v1(
        mir, veyra, envelope, veil_key=VEIL
    )
    grant = mint_reconstruction_grant_v1(
        mir,
        veyra,
        envelope,
        request,
        grant_id="effect-materialization-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    epoch_state = backing if backing is not None else {}
    epoch_state.setdefault("epoch", 7)
    continuity = bind_continuity_epoch_authority_v1(
        continuity_id="materialization-galaxy-continuity",
        epoch_reader=lambda: epoch_state["epoch"],
    )

    black_hole = DurableBlackHole(Path(directory) / "black-hole.sqlite3")
    matrix_horizon = DurableMatrixHorizonFence(Path(directory) / "matrix-horizon.sqlite3")
    coordinator = AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3")
    coordinator.initialize(initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7))
    matrix_horizon.initialize(matrix_admission)

    registry = CanonicalMaterializationRegistryV1(materialization_key=MATERIALIZE)
    reconstruct_gate = RepresentationReconstructionGateV1(
        representation=representation,
        hidden_mir=mir,
        veyra=veyra,
        envelope=envelope,
        grant=grant,
        request=request,
        veil_key=VEIL,
        reconstruction_key=RECON,
        receipt_key=RECEIPT,
        continuity=continuity,
        ledger=ReconstructionConsumptionLedgerV1(),
        materialization_registry=registry,
    )
    galaxy = GalaxyMaterializationContextV1(
        black_hole=black_hole,
        matrix_horizon=matrix_horizon,
        coordinator=coordinator,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        matrix_admission=matrix_admission,
        sathra=sathra,
        sathra_binding=sathra_binding,
        failure_independence=independence,
    )
    return {
        "mir": mir,
        "plan": plan,
        "proof": proof,
        "veyra": veyra,
        "aevra": aevra,
        "matrix": matrix,
        "hara": hara,
        "matrix_admission": matrix_admission,
        "request": request,
        "bound": bound,
        "sathra": sathra,
        "representation": representation,
        "grant": grant,
        "continuity": continuity,
        "registry": registry,
        "reconstruct_gate": reconstruct_gate,
        "galaxy": galaxy,
        "backing": epoch_state,
    }


def close_world(world):
    world["galaxy"].black_hole.close()
    world["galaxy"].matrix_horizon.close()
    world["galaxy"].coordinator.close()


def effect_gate(world, handle, *, request=None, proof=None, galaxy=None, purpose="execute"):
    selected_request = request or world["request"]
    selected_proof = proof or world["proof"]
    return CanonicalMaterializationEffectGateV1(
        registry=world["registry"],
        handle=handle,
        request=selected_request,
        proof=selected_proof,
        bound=bind_proof_to_request(world["mir"], selected_request, selected_proof),
        continuity=world["continuity"],
        galaxy=galaxy or world["galaxy"],
        purpose=purpose,
    )


def test_opaque_handle_executes_only_through_complete_galaxy_constitution():
    with tempfile.TemporaryDirectory() as directory:
        world = build_world(directory)
        try:
            handle, receipt = world["reconstruct_gate"].reconstruct(purpose="execute")
            calls = []
            decision, result, claim = effect_gate(world, handle).execute(
                lambda item: calls.append(item.digest) or b"signed"
            )
            assert receipt.request_binding == world["grant"].request_binding
            assert world["request"].digest not in repr(world["grant"])
            assert decision.decision == "ALLOW"
            assert result == b"signed"
            assert claim.state == "COMMITTED"
            assert calls == [world["request"].digest]
            with pytest.raises(CanonicalMaterializationHandleV1Error, match="already consumed"):
                effect_gate(world, handle).execute(lambda _: b"must-not-run")
        finally:
            close_world(world)


def test_noncanonical_khar_veyra_cannot_execute_materialized_privileged_effect():
    with tempfile.TemporaryDirectory() as directory:
        world = build_world(directory, canonical_khar=False)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            calls = []
            with pytest.raises(GalaxyExecutionError, match="canonical Khar"):
                effect_gate(world, handle).execute(lambda _: calls.append(1))
            assert calls == []
            with pytest.raises(CanonicalMaterializationHandleV1Error, match="already consumed"):
                effect_gate(world, handle).execute(lambda _: b"must-not-run")
        finally:
            close_world(world)


def test_foreign_veyra_context_rejects_before_materialization_is_consumed():
    with tempfile.TemporaryDirectory() as directory_a, tempfile.TemporaryDirectory() as directory_b:
        world = build_world(directory_a)
        foreign = build_world(directory_b)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            with pytest.raises(
                CanonicalMaterializationHandleV1Error,
                match="request/Veyra mismatch",
            ):
                effect_gate(world, handle, galaxy=foreign["galaxy"]).execute(lambda _: b"no")
            decision, result, claim = effect_gate(world, handle).execute(lambda _: b"yes")
            assert decision.decision == "ALLOW"
            assert result == b"yes"
            assert claim.state == "COMMITTED"
        finally:
            close_world(world)
            close_world(foreign)


def test_cross_request_substitution_rejects_without_consuming_handle():
    with tempfile.TemporaryDirectory() as directory:
        world = build_world(directory)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            other = request_for(world["mir"], 7, "99")
            with pytest.raises(CanonicalMaterializationHandleV1Error, match="request/Veyra mismatch"):
                effect_gate(world, handle, request=other).execute(lambda _: b"no")
            decision, result, claim = effect_gate(world, handle).execute(lambda _: b"original")
            assert decision.decision == "ALLOW"
            assert result == b"original"
            assert claim.state == "COMMITTED"
        finally:
            close_world(world)


def test_expired_handle_is_rejected_by_shared_continuity_before_galaxy_effect():
    with tempfile.TemporaryDirectory() as directory:
        world = build_world(directory)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            world["backing"]["epoch"] = 8
            calls = []
            with pytest.raises(
                CanonicalMaterializationHandleV1Error,
                match="canonical request epoch differs from current materialization epoch|expired",
            ):
                effect_gate(world, handle).execute(lambda _: calls.append(1))
            assert calls == []
        finally:
            close_world(world)


def test_denied_native_proof_is_durably_rejected_and_burns_materialization_handle():
    with tempfile.TemporaryDirectory() as directory:
        world = build_world(directory)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            denied = proof_for(world["mir"], world["plan"], "derive-least-authority")
            calls = []
            decision, result, claim = effect_gate(world, handle, proof=denied).execute(
                lambda _: calls.append(1)
            )
            assert decision.decision == "DENY"
            assert result is None
            assert claim.state == "REJECTED"
            assert calls == []
            with pytest.raises(CanonicalMaterializationHandleV1Error, match="already consumed"):
                effect_gate(world, handle).execute(lambda _: b"must-not-run")
        finally:
            close_world(world)
