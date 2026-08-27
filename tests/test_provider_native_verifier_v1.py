from dataclasses import replace
import hashlib

import pytest

from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1
from koschei.pi_finality_profile_v1 import PiFinalityProfileV1Error, verify_pi_native_payment_response_v1
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.provider_native_verifier_v1 import (
    ProviderNativeVerificationResultV1,
    ProviderNativeVerifierV1Error,
    verify_provider_native_response_v1,
)
from koschei.verifier_build_provenance_v1 import (
    VerifierBuildProvenanceV1Error,
    admit_verifier_artifact_v1,
    attest_verifier_build_v1,
    measure_verifier_artifact_v1,
)

_RESULT_CTX = b"koschei.effect-result-measurement/v1\x00"


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def effect_chain(txid=b"pi-tx-abc"):
    measurement = hashlib.sha256(_RESULT_CTX + txid).hexdigest()
    receipt = EffectExecutionReceiptV1(
        consumption_receipt_digest=h("consume"), permit_digest=h("permit"),
        authorization_decision_digest=h("decision"), canonical_request_digest=h("request"),
        operation="subscription.enable", execution_epoch=70, outcome="effect-completed",
        measurement_digest=measurement, receipt_digest=h("effect-receipt"),
    )
    envelope = EffectExecutionProofEnvelopeV1(
        base_execution_envelope_digest=h("base"), effect_receipt_digest=receipt.receipt_digest,
        canonical_request_digest=receipt.canonical_request_digest, operation=receipt.operation,
        epoch=70, terminal_state="effect-completed", measurement_digest=measurement,
        envelope_digest=h("effect-envelope"),
    )
    return txid, receipt, envelope


def admitted(provider="pi"):
    artifact = b"compiled-pi-verifier-artifact-v1"
    bk, ak = b"b" * 32, b"a" * 32
    provenance = attest_verifier_build_v1(
        artifact_bytes=artifact, build_input_digest=h("verifier-source-ir"),
        toolchain_digest=h("toolchain-v1"), build_profile="release-reproducible",
        build_provenance_key=bk,
    )
    abi = seal_provider_adapter_abi_v1(
        provider_id=provider, adapter_id="pi-payment-verifier",
        schema_id="pi-payment-backend", schema_version="opaque-v1",
        verifier_implementation_digest=measure_verifier_artifact_v1(artifact),
    )
    admission = admit_verifier_artifact_v1(
        provenance=provenance, artifact_bytes=artifact, adapter_abi=abi,
        build_provenance_key=bk, runtime_admission_key=ak,
    )
    return artifact, bk, ak, provenance, abi, admission


def verifier_for(reference, state="finalized"):
    return lambda raw: ProviderNativeVerificationResultV1(
        reference_bytes=reference, proof_bytes=b"proof:" + raw, state=state,
    )


def verify(*, txid=b"pi-tx-abc", raw=b"opaque-response", artifact_override=None):
    txid, receipt, envelope = effect_chain(txid)
    artifact, bk, ak, provenance, abi, admission = admitted()
    actual_artifact = artifact if artifact_override is None else artifact_override
    key = b"n" * 32
    native = verify_provider_native_response_v1(
        provider_id="pi", adapter_abi=abi, runtime_admission=admission,
        provenance=provenance, verifier_artifact_bytes=actual_artifact,
        build_provenance_key=bk, runtime_admission_key=ak,
        effect_envelope=envelope, effect_receipt=receipt, effect_result_bytes=txid,
        raw_response_bytes=raw, observed_epoch=71, verifier=verifier_for(txid),
        provider_native_verifier_key=key,
    )
    return locals()


def test_exact_loaded_artifact_is_bound_before_provider_verifier_runs():
    x = verify()
    assert x["native"].runtime_admission_digest == x["admission"].admission_digest
    assert x["native"].verifier_implementation_digest == x["abi"].verifier_implementation_digest


def test_changed_loaded_artifact_rejects_before_verifier_callback():
    txid, receipt, envelope = effect_chain()
    artifact, bk, ak, provenance, abi, admission = admitted()
    calls = []
    with pytest.raises(VerifierBuildProvenanceV1Error, match="artifact"):
        verify_provider_native_response_v1(
            provider_id="pi", adapter_abi=abi, runtime_admission=admission,
            provenance=provenance, verifier_artifact_bytes=b"malicious-verifier",
            build_provenance_key=bk, runtime_admission_key=ak,
            effect_envelope=envelope, effect_receipt=receipt, effect_result_bytes=txid,
            raw_response_bytes=b"raw", observed_epoch=71,
            verifier=lambda raw: calls.append(1) or verifier_for(txid)(raw),
            provider_native_verifier_key=b"n" * 32,
        )
    assert calls == []


def test_abi_cannot_claim_different_verifier_artifact():
    artifact, bk, ak, provenance, _, _ = admitted()
    fake_abi = seal_provider_adapter_abi_v1(
        provider_id="pi", adapter_id="pi-payment-verifier", schema_id="pi-payment-backend",
        schema_version="opaque-v1", verifier_implementation_digest=h("fake-good-verifier"),
    )
    with pytest.raises(VerifierBuildProvenanceV1Error, match="adapter ABI implementation"):
        admit_verifier_artifact_v1(
            provenance=provenance, artifact_bytes=artifact, adapter_abi=fake_abi,
            build_provenance_key=bk, runtime_admission_key=ak,
        )


def test_build_provenance_tampering_rejects():
    artifact, bk, ak, provenance, abi, admission = admitted()
    forged = replace(provenance, toolchain_digest=h("other-toolchain"))
    with pytest.raises(VerifierBuildProvenanceV1Error, match="authentication failed"):
        forged.assert_authenticated(build_provenance_key=bk, artifact_bytes=artifact)


def test_raw_response_and_reference_rebinding_still_reject():
    x = verify()
    with pytest.raises(ProviderNativeVerifierV1Error, match="raw response mismatch"):
        x["native"].assert_authenticated(
            provider_native_verifier_key=x["key"], adapter_abi=x["abi"],
            runtime_admission=x["admission"], provenance=x["provenance"],
            verifier_artifact_bytes=x["artifact"], build_provenance_key=x["bk"],
            runtime_admission_key=x["ak"], effect_envelope=x["envelope"],
            effect_receipt=x["receipt"], effect_result_bytes=x["txid"],
            raw_response_bytes=b"other-response",
        )


def test_pi_profile_requires_admitted_pi_verifier_artifact():
    txid, receipt, envelope = effect_chain()
    artifact, bk, ak, provenance, abi, admission = admitted()
    native = verify_pi_native_payment_response_v1(
        adapter_abi=abi, runtime_admission=admission, provenance=provenance,
        verifier_artifact_bytes=artifact, build_provenance_key=bk, runtime_admission_key=ak,
        effect_envelope=envelope, effect_receipt=receipt, effect_result_txid_bytes=txid,
        raw_pi_response_bytes=b"raw", observed_epoch=71, verifier=verifier_for(txid),
        provider_native_verifier_key=b"n" * 32,
    )
    assert native.provider_id == "pi"
    bad_artifact, bad_bk, bad_ak, bad_prov, bad_abi, bad_admission = admitted(provider="other")
    with pytest.raises(PiFinalityProfileV1Error, match="provider_id=pi"):
        verify_pi_native_payment_response_v1(
            adapter_abi=bad_abi, runtime_admission=bad_admission, provenance=bad_prov,
            verifier_artifact_bytes=bad_artifact, build_provenance_key=bad_bk,
            runtime_admission_key=bad_ak, effect_envelope=envelope, effect_receipt=receipt,
            effect_result_txid_bytes=txid, raw_pi_response_bytes=b"raw", observed_epoch=71,
            verifier=verifier_for(txid), provider_native_verifier_key=b"n" * 32,
        )
