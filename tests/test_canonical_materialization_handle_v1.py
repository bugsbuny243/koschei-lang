from dataclasses import replace
import hashlib

import pytest

from koschei.canonical_materialization_handle_v1 import (
    CanonicalMaterializationEffectGateV1,
    CanonicalMaterializationHandleV1Error,
    CanonicalMaterializationRegistryV1,
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
from koschei.native_sigil_enforcement_gate_v1 import PrivilegedEffectIntent
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.representation_boundary_v1 import (
    issue_observable_representation_v1,
    mint_reconstruction_grant_v1,
)
from koschei.representation_reconstruction_gate_v1 import (
    ReconstructionConsumptionLedgerV1,
    RepresentationReconstructionGateV1,
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


def world():
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
    representation = issue_observable_representation_v1(
        mir, veyra, envelope, veil_key=VEIL
    )
    grant = mint_reconstruction_grant_v1(
        mir,
        veyra,
        envelope,
        grant_id="effect-materialization-1",
        purpose="execute",
        reconstruction_key=RECON,
    )
    registry = CanonicalMaterializationRegistryV1(materialization_key=MATERIALIZE)
    reconstruct_gate = RepresentationReconstructionGateV1(
        representation=representation,
        hidden_mir=mir,
        veyra=veyra,
        envelope=envelope,
        grant=grant,
        veil_key=VEIL,
        reconstruction_key=RECON,
        receipt_key=RECEIPT,
        epoch_source=lambda: envelope.visibility_epoch,
        ledger=ReconstructionConsumptionLedgerV1(),
        materialization_registry=registry,
    )
    return mir, plan, envelope, registry, reconstruct_gate


def proof_for(mir, plan, failed_obligation=None):
    receipts = tuple(
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest="evidence:" + step.binding_digest,
            success=step.obligation != failed_obligation,
        )
        for step in plan.library_plan.steps
    )
    return seal_native_sigil_proof(mir, receipts)


def intent(tag="42"):
    return PrivilegedEffectIntent(
        effect_id="withdrawal:" + tag,
        subject="withdrawal",
        operation="signer.execute",
        request_digest="request:" + tag,
    )


def test_opaque_handle_executes_native_effect_without_returning_mir():
    mir, plan, envelope, registry, reconstruct_gate = world()
    handle, _ = reconstruct_gate.reconstruct(purpose="execute")
    proof = proof_for(mir, plan)
    calls = []

    decision, result = CanonicalMaterializationEffectGateV1(
        registry=registry,
        handle=handle,
        proof=proof,
        intent=intent(),
        epoch_source=lambda: envelope.visibility_epoch,
    ).execute(lambda item: calls.append(item.effect_id) or b"signed")

    assert decision.decision == "ALLOW"
    assert result == b"signed"
    assert calls == ["withdrawal:42"]

    with pytest.raises(
        CanonicalMaterializationHandleV1Error,
        match="already consumed or unknown",
    ):
        CanonicalMaterializationEffectGateV1(
            registry=registry,
            handle=handle,
            proof=proof,
            intent=intent("43"),
            epoch_source=lambda: envelope.visibility_epoch,
        ).execute(lambda _: b"should-not-run")


def test_handle_tamper_rejects_before_effect_callback():
    mir, plan, envelope, registry, reconstruct_gate = world()
    handle, _ = reconstruct_gate.reconstruct(purpose="execute")
    forged = replace(handle, purpose="inspect")
    calls = []

    with pytest.raises(
        CanonicalMaterializationHandleV1Error,
        match="authentication failed",
    ):
        CanonicalMaterializationEffectGateV1(
            registry=registry,
            handle=forged,
            proof=proof_for(mir, plan),
            intent=intent(),
            epoch_source=lambda: envelope.visibility_epoch,
            purpose="inspect",
        ).execute(lambda _: calls.append(1))
    assert calls == []


def test_wrong_effect_gate_purpose_does_not_consume_valid_handle():
    mir, plan, envelope, registry, reconstruct_gate = world()
    handle, _ = reconstruct_gate.reconstruct(purpose="execute")
    proof = proof_for(mir, plan)

    with pytest.raises(
        CanonicalMaterializationHandleV1Error,
        match="purpose mismatch",
    ):
        CanonicalMaterializationEffectGateV1(
            registry=registry,
            handle=handle,
            proof=proof,
            intent=intent(),
            epoch_source=lambda: envelope.visibility_epoch,
            purpose="inspect",
        ).execute(lambda _: b"no")

    decision, result = CanonicalMaterializationEffectGateV1(
        registry=registry,
        handle=handle,
        proof=proof,
        intent=intent(),
        epoch_source=lambda: envelope.visibility_epoch,
    ).execute(lambda _: b"yes")
    assert decision.decision == "ALLOW"
    assert result == b"yes"


def test_expired_handle_does_not_open_hidden_mir_or_call_effect():
    mir, plan, envelope, registry, reconstruct_gate = world()
    handle, _ = reconstruct_gate.reconstruct(purpose="execute")
    calls = []

    with pytest.raises(CanonicalMaterializationHandleV1Error, match="expired"):
        CanonicalMaterializationEffectGateV1(
            registry=registry,
            handle=handle,
            proof=proof_for(mir, plan),
            intent=intent(),
            epoch_source=lambda: handle.expires_before_epoch,
        ).execute(lambda _: calls.append(1))
    assert calls == []


def test_denied_native_proof_burns_handle_without_running_effect():
    mir, plan, envelope, registry, reconstruct_gate = world()
    handle, _ = reconstruct_gate.reconstruct(purpose="execute")
    calls = []

    decision, result = CanonicalMaterializationEffectGateV1(
        registry=registry,
        handle=handle,
        proof=proof_for(mir, plan, "derive-least-authority"),
        intent=intent(),
        epoch_source=lambda: envelope.visibility_epoch,
    ).execute(lambda _: calls.append(1))

    assert decision.decision == "DENY"
    assert result is None
    assert calls == []

    with pytest.raises(CanonicalMaterializationHandleV1Error, match="already consumed"):
        CanonicalMaterializationEffectGateV1(
            registry=registry,
            handle=handle,
            proof=proof_for(mir, plan),
            intent=intent("again"),
            epoch_source=lambda: envelope.visibility_epoch,
        ).execute(lambda _: b"should-not-run")
