from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_veyra
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0,
    derive_adaptive_visibility_v0,
)
from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0,
    VisibilityPosture,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
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


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def veyra():
    return birth_veyra(
        profile_digest=dhex("bank-profile"),
        genesis_digest=dhex("genesis"),
        constitution_digest=dhex("khar-v1"),
        instance_digest=dhex("bank-a"),
        birth_epoch=1,
    )


def envelope():
    decision = LearningResistanceDecisionV0(
        "observer",
        d32("session"),
        1,
        10,
        3,
        2,
        0,
        1,
        300,
        VisibilityPosture.NORMAL,
        3,
        d32("decision"),
        True,
        False,
    )
    policy = VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False)
    return derive_adaptive_visibility_v0(
        decision=decision,
        policy=policy,
        current_tick=10,
        rotation_secret_commitment=d32("rotation-secret"),
    )


VEIL = b"v" * 32
RECON = b"r" * 32
RECEIPT = b"c" * 32


def world(epoch_source=None):
    m = mir()
    v = veyra()
    e = envelope()
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m,
        v,
        e,
        grant_id="execute-once-1",
        purpose="execute",
        reconstruction_key=RECON,
    )
    ledger = ReconstructionConsumptionLedgerV1()
    gate = RepresentationReconstructionGateV1(
        representation=representation,
        hidden_mir=m,
        veyra=v,
        envelope=e,
        grant=grant,
        veil_key=VEIL,
        reconstruction_key=RECON,
        receipt_key=RECEIPT,
        epoch_source=epoch_source or (lambda: e.visibility_epoch),
        ledger=ledger,
    )
    return m, v, e, representation, grant, ledger, gate


def test_trusted_gate_consumes_reconstruction_grant_once():
    m, _, e, representation, grant, _, gate = world()

    rebuilt, receipt = gate.reconstruct(purpose="execute")
    assert rebuilt is m
    assert receipt.grant_context_digest == grant.context_digest
    assert receipt.representation_digest == representation.representation_digest
    assert receipt.consumed_epoch == e.visibility_epoch
    receipt.assert_authenticated(receipt_key=RECEIPT)

    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="already consumed",
    ):
        gate.reconstruct(purpose="execute")


def test_wrong_purpose_fails_before_consumption_and_does_not_burn_grant():
    m, _, _, _, _, _, gate = world()

    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="purpose mismatch",
    ):
        gate.reconstruct(purpose="inspect")

    rebuilt, _ = gate.reconstruct(purpose="execute")
    assert rebuilt is m


def test_trusted_epoch_source_failure_is_fail_closed_and_does_not_consume():
    calls = []

    def failed_epoch():
        calls.append(1)
        raise RuntimeError("continuity unavailable")

    _, _, e, representation, grant, ledger, _ = world(epoch_source=failed_epoch)
    m = mir()
    v = veyra()
    gate = RepresentationReconstructionGateV1(
        representation=representation,
        hidden_mir=m,
        veyra=v,
        envelope=e,
        grant=grant,
        veil_key=VEIL,
        reconstruction_key=RECON,
        receipt_key=RECEIPT,
        epoch_source=failed_epoch,
        ledger=ledger,
    )
    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="trusted epoch source failed closed",
    ):
        gate.reconstruct(purpose="execute")
    assert calls == [1]


def test_invalid_boolean_epoch_is_rejected_before_consumption():
    _, _, _, _, _, _, gate = world(epoch_source=lambda: True)
    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="invalid epoch",
    ):
        gate.reconstruct(purpose="execute")


def test_expired_runtime_epoch_cannot_open_canonical_world():
    _, _, e, _, _, _, gate = world(
        epoch_source=lambda: envelope().visibility_epoch + 10
    )
    assert gate.grant.expires_before_epoch == e.visibility_epoch + 1
    with pytest.raises(RepresentationReconstructionGateV1Error, match="expired"):
        gate.reconstruct(purpose="execute")


def test_consumption_receipt_tamper_is_detected():
    _, _, _, _, _, _, gate = world()
    _, receipt = gate.reconstruct(purpose="execute")
    forged = replace(receipt, consumed_epoch=receipt.consumed_epoch + 1)
    with pytest.raises(
        RepresentationReconstructionGateV1Error,
        match="authentication failed",
    ):
        forged.assert_authenticated(receipt_key=RECEIPT)


def test_concurrent_reconstruction_has_exactly_one_success():
    _, _, _, _, _, _, gate = world()

    def invoke():
        try:
            gate.reconstruct(purpose="execute")
            return "success"
        except RepresentationReconstructionGateV1Error as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: invoke(), range(2)))

    assert outcomes.count("success") == 1
    assert sum("already consumed" in outcome for outcome in outcomes) == 1
