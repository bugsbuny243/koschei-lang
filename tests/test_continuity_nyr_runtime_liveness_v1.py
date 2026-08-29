import hashlib
import inspect

import pytest

from koschei.canonical_materialization_handle_v1 import (
    CanonicalMaterializationEffectGateV1,
    CanonicalMaterializationHandleV1Error,
    CanonicalMaterializationRegistryV1,
)
from koschei.continuity_epoch_authority_v1 import (
    ContinuityEpochAuthorityV1Error,
    bind_continuity_epoch_authority_v1,
)
from koschei.galaxy_identity_v1 import birth_veyra
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0,
    derive_adaptive_visibility_v0,
)
from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0,
    VisibilityPosture,
)
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import (
    bind_proof_to_request,
    seal_effect_request,
)
from koschei.nur_nyr_observation_gate_v1 import NyrObservationGateV1
from koschei.nur_nyr_projection_v2 import NyrProjectionV2ReplayError
from koschei.parser import parse
from koschei.representation_boundary_v1 import (
    issue_observable_representation_v1,
    mint_reconstruction_grant_v1,
)
from koschei.representation_reconstruction_gate_v1 import (
    ReconstructionConsumptionLedgerV1,
    RepresentationReconstructionGateV1,
    RepresentationReconstructionGateV1Error,
)

SOURCE = "ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;"
VEIL = b"v" * 32
RECON = b"r" * 32
RECEIPT = b"c" * 32
MATERIALIZE = b"m" * 32


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def semantic_world(backing):
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir)
    veyra = birth_veyra(
        profile_digest=dhex("profile"),
        genesis_digest=dhex("genesis"),
        constitution_digest=dhex("constitution"),
        instance_digest=dhex("instance"),
        birth_epoch=1,
    )
    decision = LearningResistanceDecisionV0(
        "observer", d32("session"), 1, 10, 3, 2, 0, 1, 300,
        VisibilityPosture.NORMAL, 3, d32("decision"), True, False,
    )
    envelope = derive_adaptive_visibility_v0(
        decision=decision,
        policy=VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False),
        current_tick=10,
        rotation_secret_commitment=d32("rotation-secret"),
    )
    backing.setdefault("epoch", envelope.visibility_epoch)
    continuity = bind_continuity_epoch_authority_v1(
        continuity_id="shared-runtime-continuity",
        epoch_reader=lambda: backing["epoch"],
    )
    representation = issue_observable_representation_v1(
        mir, veyra, envelope, veil_key=VEIL
    )
    request = seal_effect_request(
        mir,
        effect_id="withdrawal:42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=dhex("payload-42"),
        identity_digest=dhex("identity-42"),
        epoch=envelope.visibility_epoch,
        nonce_digest=dhex("nonce-42"),
    )
    grant = mint_reconstruction_grant_v1(
        mir,
        veyra,
        envelope,
        request,
        grant_id="shared-continuity-request",
        purpose="execute",
        reconstruction_key=RECON,
    )
    receipts = tuple(
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest="evidence:" + step.binding_digest,
            success=True,
        )
        for step in plan.library_plan.steps
    )
    proof = seal_native_sigil_proof(mir, receipts)
    bound = bind_proof_to_request(mir, request, proof)
    observer = NyrObservationGateV1(
        mir=mir,
        veyra=veyra,
        envelope=envelope,
        veil_key=VEIL,
        continuity=continuity,
    )
    return mir, veyra, envelope, representation, request, grant, proof, bound, observer, continuity


def reconstruction_gate(mir, veyra, envelope, representation, request, grant, continuity):
    registry = CanonicalMaterializationRegistryV1(materialization_key=MATERIALIZE)
    gate = RepresentationReconstructionGateV1(
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
    return gate, registry


def test_one_continuity_epoch_drives_all_three_sanctioned_liveness_boundaries():
    backing = {}
    (
        mir,
        veyra,
        envelope,
        representation,
        request,
        grant,
        proof,
        bound,
        observer,
        continuity,
    ) = semantic_world(backing)

    assert observer.render(representation.surface) == representation.surface.render()

    mint_gate, live_registry = reconstruction_gate(
        mir, veyra, envelope, representation, request, grant, continuity
    )
    handle, _ = mint_gate.reconstruct(purpose="execute")

    stale_gate, _ = reconstruction_gate(
        mir, veyra, envelope, representation, request, grant, continuity
    )
    effect_gate = CanonicalMaterializationEffectGateV1(
        registry=live_registry,
        handle=handle,
        request=request,
        proof=proof,
        bound=bound,
        continuity=continuity,
    )

    backing["epoch"] = envelope.visibility_epoch + 1

    with pytest.raises(NyrProjectionV2ReplayError, match="expired"):
        observer.render(representation.surface)

    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="canonical request epoch differs from current reconstruction epoch",
    ):
        stale_gate.reconstruct(purpose="execute")

    calls = []
    with pytest.raises(
        CanonicalMaterializationHandleV1Error,
        match="canonical request epoch differs from current materialization epoch|expired",
    ):
        effect_gate.execute(lambda _: calls.append(1))
    assert calls == []


def test_one_failed_continuity_reader_fails_all_three_boundaries_closed():
    good_backing = {}
    (
        mir,
        veyra,
        envelope,
        representation,
        request,
        grant,
        proof,
        bound,
        _,
        good_continuity,
    ) = semantic_world(good_backing)
    mint_gate, registry = reconstruction_gate(
        mir, veyra, envelope, representation, request, grant, good_continuity
    )
    handle, _ = mint_gate.reconstruct(purpose="execute")

    def failed_reader():
        raise RuntimeError("continuity unavailable")

    failed = bind_continuity_epoch_authority_v1(
        continuity_id="shared-runtime-continuity",
        epoch_reader=failed_reader,
    )
    observer = NyrObservationGateV1(
        mir=mir,
        veyra=veyra,
        envelope=envelope,
        veil_key=VEIL,
        continuity=failed,
    )
    stale_gate, _ = reconstruction_gate(
        mir, veyra, envelope, representation, request, grant, failed
    )
    effect_gate = CanonicalMaterializationEffectGateV1(
        registry=registry,
        handle=handle,
        request=request,
        proof=proof,
        bound=bound,
        continuity=failed,
    )

    for operation in (
        lambda: observer.render(representation.surface),
        lambda: stale_gate.reconstruct(purpose="execute"),
        lambda: effect_gate.execute(lambda _: b"must-not-run"),
    ):
        with pytest.raises(ContinuityEpochAuthorityV1Error, match="read failed closed"):
            operation()


def test_invalid_boolean_epoch_is_rejected_by_shared_continuity():
    continuity = bind_continuity_epoch_authority_v1(
        continuity_id="invalid-runtime-continuity",
        epoch_reader=lambda: True,
    )
    with pytest.raises(ContinuityEpochAuthorityV1Error, match="invalid epoch"):
        continuity.current_epoch()


def test_sanctioned_gate_signatures_expose_continuity_not_raw_epoch_source():
    for gate_type in (
        NyrObservationGateV1,
        RepresentationReconstructionGateV1,
        CanonicalMaterializationEffectGateV1,
    ):
        parameters = inspect.signature(gate_type).parameters
        assert "continuity" in parameters
        assert "epoch_source" not in parameters
