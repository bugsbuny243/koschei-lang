from dataclasses import replace
import hashlib
import pytest
from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1
from koschei.pi_finality_profile_v1 import PiFinalityProfileV1Error, issue_pi_finality_verdict_v1, verify_pi_native_payment_response_v1
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.provider_native_verifier_v1 import ProviderNativeVerificationResultV1, ProviderNativeVerifierV1Error, verify_provider_native_response_v1
_RESULT_CTX=b"koschei.effect-result-measurement/v1\x00"
def h(tag): return hashlib.sha256(tag.encode()).hexdigest()
def abi(tag="v1"): return seal_provider_adapter_abi_v1(provider_id="pi",adapter_id="pi-payment-finality",schema_id="opaque-pi-payment-response",schema_version=tag,verifier_implementation_digest=h("pi-verifier-"+tag))
def effect_chain(txid=b"pi-tx-abc"):
    measurement=hashlib.sha256(_RESULT_CTX+txid).hexdigest(); receipt=EffectExecutionReceiptV1(h("consume"),h("permit"),h("decision"),h("request"),"subscription.enable",70,"effect-completed",measurement,h("effect-receipt")); envelope=EffectExecutionProofEnvelopeV1(h("base"),receipt.receipt_digest,receipt.canonical_request_digest,receipt.operation,receipt.execution_epoch,"effect-completed",measurement,h("effect-envelope")); return txid,receipt,envelope
def verifier_for(reference,state="finalized",proof=b"provider-proof"):
    return lambda raw: ProviderNativeVerificationResultV1(reference,proof,state)
def make_native(raw=b"raw",adapter=None):
    txid,receipt,envelope=effect_chain(); adapter=adapter or abi(); key=b"n"*32
    native=verify_provider_native_response_v1(provider_id="pi",adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=raw,observed_epoch=71,verifier=verifier_for(txid),provider_native_verifier_key=key)
    return txid,receipt,envelope,adapter,key,native

def test_raw_provider_response_is_bound_to_exact_effect_result_and_abi():
    txid,receipt,envelope,adapter,key,native=make_native()
    native.assert_authenticated(provider_native_verifier_key=key,adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw")
    assert native.adapter_abi_digest==adapter.abi_digest
    assert native.verifier_implementation_digest==adapter.verifier_implementation_digest
    assert native.authority is False

def test_wrong_reference_from_provider_verifier_is_rejected():
    txid,receipt,envelope=effect_chain()
    with pytest.raises(ProviderNativeVerifierV1Error,match="differs from effect result"):
        verify_provider_native_response_v1(provider_id="pi",adapter_abi=abi(),effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw",observed_epoch=71,verifier=verifier_for(b"different"),provider_native_verifier_key=b"n"*32)

def test_raw_response_rebinding_breaks_native_receipt():
    txid,receipt,envelope,adapter,key,native=make_native(b"raw-a")
    with pytest.raises(ProviderNativeVerifierV1Error,match="raw response mismatch"):
        native.assert_authenticated(provider_native_verifier_key=key,adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw-b")

def test_receipt_cannot_move_to_different_schema_or_verifier_implementation():
    txid,receipt,envelope,adapter,key,native=make_native()
    with pytest.raises(ProviderNativeVerifierV1Error):
        native.assert_authenticated(provider_native_verifier_key=key,adapter_abi=abi("v2"),effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw")

def test_native_receipt_identity_or_state_tampering_rejects():
    txid,receipt,envelope,adapter,key,native=make_native()
    for forged in (replace(native,state="rejected"),replace(native,adapter_abi_digest=h("fake")),replace(native,verifier_implementation_digest=h("fake-impl"))):
        with pytest.raises(ProviderNativeVerifierV1Error): forged.assert_authenticated(provider_native_verifier_key=key,adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw")

def test_pi_profile_derives_verdict_only_from_authenticated_abi_bound_receipt():
    txid,receipt,envelope=effect_chain(); adapter=abi(); nk,vk=b"n"*32,b"v"*32; raw=b"opaque-pi"
    native=verify_pi_native_payment_response_v1(adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_txid_bytes=txid,raw_pi_response_bytes=raw,observed_epoch=71,verifier=verifier_for(txid),provider_native_verifier_key=nk)
    verdict=issue_pi_finality_verdict_v1(native_receipt=native,adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_txid_bytes=txid,raw_pi_response_bytes=raw,provider_native_verifier_key=nk,provider_verifier_key=vk)
    assert verdict.provider_id=="pi" and verdict.state=="finalized"

def test_pi_verdict_rejects_different_adapter_abi():
    txid,receipt,envelope=effect_chain(); adapter=abi(); nk,vk=b"n"*32,b"v"*32; raw=b"opaque-pi"
    native=verify_pi_native_payment_response_v1(adapter_abi=adapter,effect_envelope=envelope,effect_receipt=receipt,effect_result_txid_bytes=txid,raw_pi_response_bytes=raw,observed_epoch=71,verifier=verifier_for(txid),provider_native_verifier_key=nk)
    with pytest.raises(PiFinalityProfileV1Error): issue_pi_finality_verdict_v1(native_receipt=native,adapter_abi=abi("v2"),effect_envelope=envelope,effect_receipt=receipt,effect_result_txid_bytes=txid,raw_pi_response_bytes=raw,provider_native_verifier_key=nk,provider_verifier_key=vk)
