from dataclasses import replace
import hashlib

import pytest

from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.pi_finality_profile_v1 import PiFinalityProfileV1Error, verify_pi_native_payment_response_v1
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.provider_native_verifier_v1 import (
    ProviderNativeVerificationResultV1,
    ProviderNativeVerifierV1Error,
    verify_provider_native_response_v1,
)
from koschei.verified_ir_build_input_v1 import (
    VerifiedIrBuildInputV1Error,
    derive_verified_ir_build_input_v1,
)
from koschei.verifier_build_provenance_v1 import (
    VerifierBuildProvenanceV1Error,
    admit_verifier_artifact_v1,
    attest_verifier_build_from_verified_ir_v1,
    measure_verifier_artifact_v1,
)

_RESULT_CTX = b"koschei.effect-result-measurement/v1\x00"
VERIFIER_SOURCE = """
ka provider;
shi proof;
nur visibility;
"""


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def verified_build_input(source=VERIFIER_SOURCE):
    mir = lower_native_sigils(parse(source))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [
        make_receipt(
            activation_step_id=s.activation_step_id,
            obligation=s.obligation,
            subsystem=s.subsystem,
            proof_kind=s.proof_kind,
            evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),
            success=True,
        )
        for s in plan.steps
    ]
    proof = seal_native_sigil_proof(mir, receipts)
    verified_input = derive_verified_ir_build_input_v1(mir=mir, proof=proof)
    return mir, proof, verified_input


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
    verifier_mir, verifier_proof, verified_input = verified_build_input()
    provenance = attest_verifier_build_from_verified_ir_v1(
        verified_input=verified_input,
        mir=verifier_mir,
        proof=verifier_proof,
        artifact_bytes=artifact,
        toolchain_digest=h("toolchain-v1"),
        build_profile="release-reproducible",
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
    return artifact, bk, ak, provenance, abi, admission, verifier_mir, verifier_proof, verified_input


def verifier_for(reference, state="finalized"):
    return lambda raw: ProviderNativeVerificationResultV1(
        reference_bytes=reference, proof_bytes=b"proof:" + raw, state=state,
    )


def verify(*, txid=b"pi-tx-abc", raw=b"opaque-response", artifact_override=None):
    txid, receipt, envelope = effect_chain(txid)
    artifact, bk, ak, provenance, abi, admission, verifier_mir, verifier_proof, verified_input = admitted()
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


def test_build_input_is_derived_from_sealed_native_ir_and_proof():
    _, _, _, provenance, _, _, mir, proof, verified_input = admitted()
    verified_input.assert_sealed(mir=mir, proof=proof)
    assert provenance.build_input_digest == verified_input.build_input_digest
    assert verified_input.native_mir_fingerprint == mir.fingerprint
    assert verified_input.native_proof_digest == proof.digest
    assert verified_input.authority is False


def test_verified_ir_build_input_cannot_move_to_different_mir_or_proof():
    _, _, verified_input = verified_build_input()
    other_mir, other_proof, _ = verified_build_input("ka other;\nshi proof;\nnur visibility;\n")
    with pytest.raises(VerifiedIrBuildInputV1Error):
        verified_input.assert_sealed(mir=other_mir, proof=other_proof)


def test_build_provenance_rejects_foreign_verified_input():
    artifact, bk, _, provenance, _, _, _, _, _ = admitted()
    other_mir, other_proof, other_input = verified_build_input("ka other;\nshi proof;\nnur visibility;\n")
    with pytest.raises(VerifierBuildProvenanceV1Error, match="does not derive"):
        provenance.assert_from_verified_ir(
            verified_input=other_input, mir=other_mir, proof=other_proof,
            build_provenance_key=bk, artifact_bytes=artifact,
        )


def test_exact_loaded_artifact_is_bound_before_provider_verifier_runs():
    x = verify()
    assert x["native"].runtime_admission_digest == x["admission"].admission_digest
    assert x["native"].verifier_implementation_digest == x["abi"].verifier_implementation_digest


def test_changed_loaded_artifact_rejects_before_verifier_callback():
    txid, receipt, envelope = effect_chain()
    artifact, bk, ak, provenance, abi, admission, *_ = admitted()
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
    artifact, bk, ak, provenance, _, _, *_ = admitted()
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
    artifact, bk, _, provenance, *_ = admitted()
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
    artifact, bk, ak, provenance, abi, admission, *_ = admitted()
    native = verify_pi_native_payment_response_v1(
        adapter_abi=abi, runtime_admission=admission, provenance=provenance,
        verifier_artifact_bytes=artifact, build_provenance_key=bk, runtime_admission_key=ak,
        effect_envelope=envelope, effect_receipt=receipt, effect_result_txid_bytes=txid,
        raw_pi_response_bytes=b"raw", observed_epoch=71, verifier=verifier_for(txid),
        provider_native_verifier_key=b"n" * 32,
    )
    assert native.provider_id == "pi"
    bad_artifact, bad_bk, bad_ak, bad_prov, bad_abi, bad_admission, *_ = admitted(provider="other")
    with pytest.raises(PiFinalityProfileV1Error, match="provider_id=pi"):
        verify_pi_native_payment_response_v1(
            adapter_abi=bad_abi, runtime_admission=bad_admission, provenance=bad_prov,
            verifier_artifact_bytes=bad_artifact, build_provenance_key=bad_bk,
            runtime_admission_key=bad_ak, effect_envelope=envelope, effect_receipt=receipt,
            effect_result_txid_bytes=txid, raw_pi_response_bytes=b"raw", observed_epoch=71,
            verifier=verifier_for(txid), provider_native_verifier_key=b"n" * 32,
        )
