from dataclasses import replace
import hashlib
import pytest
from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import canonical_subject_scope_digest_v1, derive_canonical_authority_basis_v1
from koschei.effect_execution_proof_envelope_v1 import seal_effect_execution_proof_envelope_v1
from koschei.effect_execution_receipt_v1 import execute_effect_with_receipt_v1
from koschei.execution_permit_v1 import ExecutionPermitLedgerV1, mint_execution_permit_v1
from koschei.execution_proof_envelope_v1 import seal_execution_proof_envelope_v1
from koschei.external_adapter_contract_v1 import admit_external_adapter_evidence_v1, issue_external_adapter_grant_v1
from koschei.external_finality_attestation_v1 import attest_external_finality_v1
from koschei.external_finality_proof_envelope_v1 import ExternalFinalityProofEnvelopeV1Error, seal_external_finality_proof_envelope_v1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.pi_finality_profile_v1 import issue_pi_finality_verdict_v1, verify_pi_native_payment_response_v1
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.provider_native_verifier_v1 import ProviderNativeVerificationResultV1
SOURCE="""ka treasury;\nvor withdrawal;\nshi evidence;\nthal recovery;\nnur visibility;\n"""
def h(tag): return hashlib.sha256(tag.encode()).hexdigest()
def chain(finality_state="finalized"):
    mir=lower_native_sigils(parse(SOURCE)); plan=expand_native_sigil_mir(mir).library_plan
    receipts=[make_receipt(activation_step_id=s.activation_step_id,obligation=s.obligation,subsystem=s.subsystem,proof_kind=s.proof_kind,evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),success=True) for s in plan.steps]
    proof=seal_native_sigil_proof(mir,receipts); request=seal_effect_request(mir,effect_id="pi-finality-71",subject="withdrawal",operation="subscription.enable",request_digest=h("payload-71"),identity_digest=h("pi-user-71"),epoch=71,nonce_digest=h("nonce-71")); bound=bind_proof_to_request(mir,request,proof); basis=derive_canonical_authority_basis_v1(mir=mir,request=request,proof=proof,bound=bound)
    grant=issue_external_adapter_grant_v1(provider_id="pi",consumer_id="koschei-lab-pi",subject_scope_digest=canonical_subject_scope_digest_v1(request),allowed_actions=("payment.observe",),valid_from_epoch=71,expires_before_epoch=72); evidence=admit_external_adapter_evidence_v1(grant,action="payment.observe",external_evidence_digest=h("settled-payment-71"),observed_epoch=71)
    dk,rk,ek,nk,vk,fk=b"d"*32,b"r"*32,b"e"*32,b"n"*32,b"v"*32,b"f"*32
    decision=issue_authorization_decision_v1(grant,evidence,basis,mir=mir,request=request,proof=proof,bound=bound,decision_key=dk); permit=mint_execution_permit_v1(grant,evidence,decision,runtime_key=rk,decision_key=dk); txid=b"pi-transaction-reference:71"
    consumption,effect_receipt,effect_result=execute_effect_with_receipt_v1(ledger=ExecutionPermitLedgerV1(),permit=permit,runtime_key=rk,decision_key=dk,effect_key=ek,grant=grant,evidence=evidence,decision=decision,mir=mir,request=request,current_epoch=71,effect=lambda _:txid)
    base=seal_execution_proof_envelope_v1(grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,decision_key=dk,runtime_key=rk)
    effect_envelope=seal_effect_execution_proof_envelope_v1(base=base,effect_receipt=effect_receipt,grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,decision_key=dk,runtime_key=rk,effect_key=ek)
    adapter_abi=seal_provider_adapter_abi_v1(provider_id="pi",adapter_id="pi-payment-finality",schema_id="opaque-pi-payment-response",schema_version="v1",verifier_implementation_digest=h("pi-verifier-v1")); raw_pi_response=b"opaque-pi-backend-response:71"
    native_receipt=verify_pi_native_payment_response_v1(adapter_abi=adapter_abi,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_txid_bytes=effect_result,raw_pi_response_bytes=raw_pi_response,observed_epoch=72,verifier=lambda raw:ProviderNativeVerificationResultV1(txid,b"canonical-pi-provider-proof:71:"+raw,finality_state),provider_native_verifier_key=nk)
    verdict=issue_pi_finality_verdict_v1(native_receipt=native_receipt,adapter_abi=adapter_abi,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_txid_bytes=effect_result,raw_pi_response_bytes=raw_pi_response,provider_native_verifier_key=nk,provider_verifier_key=vk)
    attestation=attest_external_finality_v1(effect_envelope=effect_envelope,verdict=verdict,provider_verifier_key=vk,finality_key=fk)
    finality=seal_external_finality_proof_envelope_v1(adapter_abi=adapter_abi,effect_envelope=effect_envelope,effect_receipt=effect_receipt,effect_result_bytes=effect_result,raw_provider_response_bytes=raw_pi_response,native_receipt=native_receipt,base=base,grant=grant,evidence=evidence,mir=mir,request=request,proof=proof,bound=bound,basis=basis,decision=decision,permit=permit,consumption=consumption,verdict=verdict,attestation=attestation,decision_key=dk,runtime_key=rk,effect_key=ek,provider_native_verifier_key=nk,provider_verifier_key=vk,finality_key=fk)
    return locals()
def validate(x,envelope=None,raw_response=None,adapter_abi=None):
    (envelope or x["finality"]).assert_valid(adapter_abi=adapter_abi or x["adapter_abi"],effect_envelope=x["effect_envelope"],effect_receipt=x["effect_receipt"],effect_result_bytes=x["effect_result"],raw_provider_response_bytes=raw_response or x["raw_pi_response"],native_receipt=x["native_receipt"],base=x["base"],grant=x["grant"],evidence=x["evidence"],mir=x["mir"],request=x["request"],proof=x["proof"],bound=x["bound"],basis=x["basis"],decision=x["decision"],permit=x["permit"],consumption=x["consumption"],verdict=x["verdict"],attestation=x["attestation"],decision_key=x["dk"],runtime_key=x["rk"],effect_key=x["ek"],provider_native_verifier_key=x["nk"],provider_verifier_key=x["vk"],finality_key=x["fk"])
def test_provider_finalized_requires_abi_native_verification_and_full_chain():
    x=chain(); validate(x); x["finality"].assert_finalized(); assert x["finality"].provider_adapter_abi_digest==x["adapter_abi"].abi_digest; assert x["finality"].verifier_implementation_digest==x["adapter_abi"].verifier_implementation_digest; assert x["finality"].authority is False
def test_pending_provider_state_cannot_be_promoted_to_finalized():
    x=chain("pending"); validate(x)
    with pytest.raises(ExternalFinalityProofEnvelopeV1Error,match="not proven"): x["finality"].assert_finalized()
def test_finality_envelope_relabel_reference_or_abi_rebinding_is_rejected():
    x=chain()
    for forged in (replace(x["finality"],terminal_state="provider-rejected"),replace(x["finality"],external_reference_digest=h("other")),replace(x["finality"],provider_adapter_abi_digest=h("other-abi"))):
        with pytest.raises(ExternalFinalityProofEnvelopeV1Error): validate(x,forged)
def test_full_finality_proof_rejects_different_raw_response_or_abi():
    x=chain()
    with pytest.raises(ValueError,match="raw response mismatch"): validate(x,raw_response=b"different")
    other=seal_provider_adapter_abi_v1(provider_id="pi",adapter_id="pi-payment-finality",schema_id="opaque-pi-payment-response",schema_version="v2",verifier_implementation_digest=h("pi-verifier-v2"))
    with pytest.raises(ValueError): validate(x,adapter_abi=other)
