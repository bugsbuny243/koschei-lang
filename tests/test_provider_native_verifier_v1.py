from dataclasses import replace
import hashlib

import pytest

from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1
from koschei.pi_finality_profile_v1 import (
    PiFinalityProfileV1Error,
    issue_pi_finality_verdict_v1,
    verify_pi_native_payment_response_v1,
)
from koschei.provider_native_verifier_v1 import (
    ProviderNativeVerificationResultV1,
    ProviderNativeVerifierV1Error,
    verify_provider_native_response_v1,
)

_RESULT_CTX = b"koschei.effect-result-measurement/v1\x00"


def h(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def effect_chain(txid: bytes = b"pi-tx-abc"):
    measurement = hashlib.sha256(_RESULT_CTX + txid).hexdigest()
    receipt = EffectExecutionReceiptV1(
        consumption_receipt_digest=h("consume"),
        permit_digest=h("permit"),
        authorization_decision_digest=h("decision"),
        canonical_request_digest=h("request"),
        operation="subscription.enable",
        execution_epoch=70,
        outcome="effect-completed",
        measurement_digest=measurement,
        receipt_digest=h("effect-receipt"),
    )
    envelope = EffectExecutionProofEnvelopeV1(
        base_execution_envelope_digest=h("base"),
        effect_receipt_digest=receipt.receipt_digest,
        canonical_request_digest=receipt.canonical_request_digest,
        operation=receipt.operation,
        epoch=receipt.execution_epoch,
        terminal_state="effect-completed",
        measurement_digest=measurement,
        envelope_digest=h("effect-envelope"),
    )
    return txid, receipt, envelope


def verifier_for(reference: bytes, *, state="finalized", proof=b"provider-proof"):
    def verify(raw: bytes):
        assert raw
        return ProviderNativeVerificationResultV1(
            reference_bytes=reference,
            proof_bytes=proof,
            state=state,
        )
    return verify


def test_raw_provider_response_is_bound_to_exact_effect_result_reference():
    txid, receipt, envelope = effect_chain()
    raw = b"opaque-provider-response"
    key = b"n" * 32
    native = verify_provider_native_response_v1(
        provider_id="pi",
        effect_envelope=envelope,
        effect_receipt=receipt,
        effect_result_bytes=txid,
        raw_response_bytes=raw,
        observed_epoch=71,
        verifier=verifier_for(txid),
        provider_native_verifier_key=key,
    )
    native.assert_authenticated(
        provider_native_verifier_key=key,
        effect_envelope=envelope,
        effect_receipt=receipt,
        effect_result_bytes=txid,
        raw_response_bytes=raw,
    )
    assert native.provider_id == "pi"
    assert native.state == "finalized"
    assert native.authority is False


def test_wrong_reference_from_provider_verifier_is_rejected():
    txid, receipt, envelope = effect_chain()
    with pytest.raises(ProviderNativeVerifierV1Error, match="differs from effect result"):
        verify_provider_native_response_v1(
            provider_id="pi",
            effect_envelope=envelope,
            effect_receipt=receipt,
            effect_result_bytes=txid,
            raw_response_bytes=b"raw",
            observed_epoch=71,
            verifier=verifier_for(b"different-txid"),
            provider_native_verifier_key=b"n" * 32,
        )


def test_raw_response_rebinding_breaks_native_receipt():
    txid, receipt, envelope = effect_chain()
    key = b"n" * 32
    native = verify_provider_native_response_v1(
        provider_id="pi", effect_envelope=envelope, effect_receipt=receipt,
        effect_result_bytes=txid, raw_response_bytes=b"raw-a", observed_epoch=71,
        verifier=verifier_for(txid), provider_native_verifier_key=key,
    )
    with pytest.raises(ProviderNativeVerifierV1Error, match="raw response mismatch"):
        native.assert_authenticated(
            provider_native_verifier_key=key, effect_envelope=envelope,
            effect_receipt=receipt, effect_result_bytes=txid,
            raw_response_bytes=b"raw-b",
        )


def test_native_receipt_state_or_reference_tampering_rejects():
    txid, receipt, envelope = effect_chain()
    key = b"n" * 32
    native = verify_provider_native_response_v1(
        provider_id="pi", effect_envelope=envelope, effect_receipt=receipt,
        effect_result_bytes=txid, raw_response_bytes=b"raw", observed_epoch=71,
        verifier=verifier_for(txid), provider_native_verifier_key=key,
    )
    for forged in (
        replace(native, state="rejected"),
        replace(native, verified_reference_digest=h("fake-reference")),
    ):
        with pytest.raises(ProviderNativeVerifierV1Error):
            forged.assert_authenticated(
                provider_native_verifier_key=key, effect_envelope=envelope,
                effect_receipt=receipt, effect_result_bytes=txid,
                raw_response_bytes=b"raw",
            )


def test_pi_profile_derives_verdict_only_from_authenticated_native_receipt():
    txid, receipt, envelope = effect_chain()
    native_key, verdict_key = b"n" * 32, b"v" * 32
    raw = b"opaque-pi-backend-response"
    native = verify_pi_native_payment_response_v1(
        effect_envelope=envelope,
        effect_receipt=receipt,
        effect_result_txid_bytes=txid,
        raw_pi_response_bytes=raw,
        observed_epoch=71,
        verifier=verifier_for(txid, state="finalized"),
        provider_native_verifier_key=native_key,
    )
    verdict = issue_pi_finality_verdict_v1(
        native_receipt=native,
        effect_envelope=envelope,
        effect_receipt=receipt,
        effect_result_txid_bytes=txid,
        raw_pi_response_bytes=raw,
        provider_native_verifier_key=native_key,
        provider_verifier_key=verdict_key,
    )
    assert verdict.provider_id == "pi"
    assert verdict.state == native.state == "finalized"
    assert verdict.external_reference_digest == native.verified_reference_digest
    assert verdict.provider_proof_digest == native.provider_proof_digest


def test_pi_verdict_rejects_wrong_effect_txid_or_raw_response():
    txid, receipt, envelope = effect_chain()
    native_key, verdict_key = b"n" * 32, b"v" * 32
    raw = b"opaque-pi-backend-response"
    native = verify_pi_native_payment_response_v1(
        effect_envelope=envelope, effect_receipt=receipt,
        effect_result_txid_bytes=txid, raw_pi_response_bytes=raw,
        observed_epoch=71, verifier=verifier_for(txid),
        provider_native_verifier_key=native_key,
    )
    with pytest.raises(PiFinalityProfileV1Error):
        issue_pi_finality_verdict_v1(
            native_receipt=native, effect_envelope=envelope, effect_receipt=receipt,
            effect_result_txid_bytes=b"different-txid", raw_pi_response_bytes=raw,
            provider_native_verifier_key=native_key, provider_verifier_key=verdict_key,
        )
    with pytest.raises(PiFinalityProfileV1Error):
        issue_pi_finality_verdict_v1(
            native_receipt=native, effect_envelope=envelope, effect_receipt=receipt,
            effect_result_txid_bytes=txid, raw_pi_response_bytes=b"different-response",
            provider_native_verifier_key=native_key, provider_verifier_key=verdict_key,
        )
