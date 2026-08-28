import hashlib
import inspect
import pytest
from koschei.attestation_verifier_abi_v1 import seal_attestation_verifier_abi_v1
from koschei.builder_environment_attestation_v1 import attest_builder_environment_v1
from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.pi_finality_profile_v1 import verify_pi_native_payment_response_v1
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.provider_native_verifier_v1 import ProviderNativeVerificationResultV1,verify_provider_native_response_v1
from koschei.remote_attestation_evidence_v1 import RemoteAttestationVerificationResultV1,verify_remote_attestation_with_abi_v1
from koschei.toolchain_provenance_v1 import attest_toolchain_provenance_v1
from koschei.trust_anchor_admission_v1 import TrustAnchorGenerationStateV1,seal_trust_anchor_manifest_v1,admit_attestation_verifier_from_trust_anchor_v1
from koschei.verified_ir_build_input_v1 import derive_verified_ir_build_input_v1
from koschei.verifier_build_provenance_v1 import attest_verifier_build_from_verified_ir_v1,measure_verifier_artifact_v1
from koschei.verifier_reproducible_admission_v1 import admit_reproducible_verifier_artifact_v1
from koschei.verifier_reproducible_build_v1 import attest_builder_observation_v1,seal_reproducible_build_receipt_v1
_RESULT_CTX=b"koschei.effect-result-measurement/v1\x00"; _SOURCE="""ka treasury;\nvor verifier;\nshi evidence;\nthal recovery;\nnur visibility;\n"""
def h(tag): return hashlib.sha256(tag.encode()).hexdigest()
def verifier_ir():
    mir=lower_native_sigils(parse(_SOURCE)); plan=expand_native_sigil_mir(mir).library_plan
    receipts=[make_receipt(activation_step_id=s.activation_step_id,obligation=s.obligation,subsystem=s.subsystem,proof_kind=s.proof_kind,evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),success=True) for s in plan.steps]
    proof=seal_native_sigil_proof(mir,receipts); return mir,proof,derive_verified_ir_build_input_v1(mir=mir,proof=proof)
def effect_chain(txid=b"pi-tx-abc"):
    measurement=hashlib.sha256(_RESULT_CTX+txid).hexdigest(); receipt=EffectExecutionReceiptV1(h("consume"),h("permit"),h("decision"),h("request"),"subscription.enable",70,"effect-completed",measurement,h("effect-receipt")); envelope=EffectExecutionProofEnvelopeV1(h("base"),receipt.receipt_digest,receipt.canonical_request_digest,receipt.operation,70,"effect-completed",measurement,h("effect-envelope")); return txid,receipt,envelope
def toolchain(name,key_byte):
    artifact=("koschei-compiler-"+name).encode(); key=key_byte*32; return attest_toolchain_provenance_v1(toolchain_id="koschei-compiler",toolchain_version=name,toolchain_artifact_bytes=artifact,build_profile="release",toolchain_signing_key=key),artifact,key
def env(builder,suffix,keybyte,root):
    e=("env-"+suffix).encode(); w=("workload-"+builder).encode(); raw=("quote-"+suffix).encode(); verifier_artifact=("attestation-verifier-"+suffix).encode(); rkey=keybyte.upper()*32; ekey=keybyte*32; root_key=(suffix.encode()*32)[:32]; admission_key=(suffix.upper().encode()*32)[:32]; generation_state=TrustAnchorGenerationStateV1()
    attabi=seal_attestation_verifier_abi_v1(provider_id="bootstrap-test-attestor",evidence_format_id="opaque-test-quote",schema_version="v1",verifier_artifact_bytes=verifier_artifact)
    manifest=seal_trust_anchor_manifest_v1(anchor_id="offline-root-"+suffix,generation=1,abi=attabi,allowed_trust_root_ids=(root,),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=root_key)
    root_admission=admit_attestation_verifier_from_trust_anchor_v1(manifest=manifest,abi=attabi,verifier_artifact_bytes=verifier_artifact,current_epoch=71,root_signing_key=root_key,runtime_admission_key=admission_key,generation_state=generation_state)
    remote=verify_remote_attestation_with_abi_v1(abi=attabi,verifier_artifact_bytes=verifier_artifact,raw_evidence_bytes=raw,current_epoch=71,verifier=lambda _:RemoteAttestationVerificationResultV1(root,e,w,71,80),remote_attestation_verifier_key=rkey,trust_anchor_manifest=manifest,trust_anchor_admission=root_admission,root_signing_key=root_key,trust_anchor_runtime_admission_key=admission_key,trust_anchor_generation_state=generation_state)
    receipt=attest_builder_environment_v1(builder_id=builder,environment_id="env-"+suffix,environment_bytes=e,workload_bytes=w,attestation_authority_id="build-attestor",environment_attestation_key=ekey,remote_evidence=remote,raw_remote_evidence_bytes=raw,remote_attestation_verifier_key=rkey,trust_anchor_generation_state=generation_state)
    return receipt,e,w,ekey,remote,raw,rkey,attabi,verifier_artifact,manifest,root_admission,root_key,admission_key,generation_state
def admitted():
    mir,proof,verified_input=verifier_ir(); artifact=b"compiled-pi-verifier-artifact-v1"; bk,rak=b"b"*32,b"a"*32; akey,bkey,rkey,gate_key=b"1"*32,b"2"*32,b"3"*32,b"4"*32
    tc_a,tc_a_bytes,tc_a_key=toolchain("v1-a",b"x"); tc_b,tc_b_bytes,tc_b_key=toolchain("v1-b",b"y")
    env_a,env_a_bytes,work_a,env_a_key,remote_a,raw_a,remote_a_key,attabi_a,attart_a,manifest_a,root_admission_a,root_key_a,root_admission_key_a,generation_state_a=env("builder-a","a",b"m","root-a")
    env_b,env_b_bytes,work_b,env_b_key,remote_b,raw_b,remote_b_key,attabi_b,attart_b,manifest_b,root_admission_b,root_key_b,root_admission_key_b,generation_state_b=env("builder-b","b",b"n","root-b")
    provenance=attest_verifier_build_from_verified_ir_v1(verified_input=verified_input,mir=mir,proof=proof,artifact_bytes=artifact,toolchain=tc_a,toolchain_artifact_bytes=tc_a_bytes,toolchain_signing_key=tc_a_key,build_profile="release-reproducible",build_provenance_key=bk)
    abi=seal_provider_adapter_abi_v1(provider_id="pi",adapter_id="pi-payment-verifier",schema_id="pi-payment-backend",schema_version="opaque-v1",verifier_implementation_digest=measure_verifier_artifact_v1(artifact))
    obs_a=attest_builder_observation_v1(builder_id="builder-a",builder_key=akey,verified_input=verified_input,mir=mir,proof=proof,toolchain=tc_a,toolchain_artifact_bytes=tc_a_bytes,toolchain_signing_key=tc_a_key,environment=env_a,environment_bytes=env_a_bytes,workload_bytes=work_a,environment_attestation_key=env_a_key,remote_evidence=remote_a,raw_remote_evidence_bytes=raw_a,remote_attestation_verifier_key=remote_a_key,current_epoch=71,trust_anchor_generation_state=generation_state_a,artifact_bytes=artifact,build_profile="release-reproducible")
    obs_b=attest_builder_observation_v1(builder_id="builder-b",builder_key=bkey,verified_input=verified_input,mir=mir,proof=proof,toolchain=tc_b,toolchain_artifact_bytes=tc_b_bytes,toolchain_signing_key=tc_b_key,environment=env_b,environment_bytes=env_b_bytes,workload_bytes=work_b,environment_attestation_key=env_b_key,remote_evidence=remote_b,raw_remote_evidence_bytes=raw_b,remote_attestation_verifier_key=remote_b_key,current_epoch=71,trust_anchor_generation_state=generation_state_b,artifact_bytes=artifact,build_profile="release-reproducible")
    common=dict(builder_a=obs_a,builder_b=obs_b,builder_a_toolchain=tc_a,builder_b_toolchain=tc_b,builder_a_toolchain_artifact_bytes=tc_a_bytes,builder_b_toolchain_artifact_bytes=tc_b_bytes,builder_a_toolchain_signing_key=tc_a_key,builder_b_toolchain_signing_key=tc_b_key,builder_a_environment=env_a,builder_b_environment=env_b,builder_a_environment_bytes=env_a_bytes,builder_b_environment_bytes=env_b_bytes,builder_a_workload_bytes=work_a,builder_b_workload_bytes=work_b,builder_a_environment_attestation_key=env_a_key,builder_b_environment_attestation_key=env_b_key,builder_a_remote_evidence=remote_a,builder_b_remote_evidence=remote_b,builder_a_raw_remote_evidence_bytes=raw_a,builder_b_raw_remote_evidence_bytes=raw_b,builder_a_remote_attestation_verifier_key=remote_a_key,builder_b_remote_attestation_verifier_key=remote_b_key,builder_a_trust_anchor_generation_state=generation_state_a,builder_b_trust_anchor_generation_state=generation_state_b,current_epoch=71)
    repro=seal_reproducible_build_receipt_v1(reproducibility_key=rkey,builder_a_key=akey,builder_b_key=bkey,verified_input=verified_input,mir=mir,proof=proof,artifact_bytes=artifact,**common)
    base,gate=admit_reproducible_verifier_artifact_v1(reproducible_admission_key=gate_key,runtime_admission_key=rak,build_provenance_key=bk,reproducibility_key=rkey,builder_a_key=akey,builder_b_key=bkey,reproducibility_receipt=repro,build_toolchain=tc_a,build_toolchain_artifact_bytes=tc_a_bytes,build_toolchain_signing_key=tc_a_key,verified_input=verified_input,mir=mir,proof=proof,provenance=provenance,artifact_bytes=artifact,adapter_abi=abi,**common)
    return locals()
def verifier_for(reference): return lambda raw: ProviderNativeVerificationResultV1(reference,b"proof:"+raw,"finalized")
def provider_kwargs(x,txid,receipt,envelope):
    return dict(provider_id="pi",adapter_abi=x['abi'],runtime_admission=x['base'],reproducible_admission=x['gate'],reproducibility_receipt=x['repro'],reproducibility_key=x['rkey'],builder_a_generation_state=x['generation_state_a'],builder_b_generation_state=x['generation_state_b'],provenance=x['provenance'],verifier_artifact_bytes=x['artifact'],build_provenance_key=x['bk'],runtime_admission_key=x['rak'],reproducible_admission_key=x['gate_key'],effect_envelope=envelope,effect_receipt=receipt,effect_result_bytes=txid,raw_response_bytes=b"raw",observed_epoch=71,provider_native_verifier_key=b"n"*32)
def test_sanctioned_build_apis_do_not_accept_raw_toolchain_digest():
    assert "toolchain_digest" not in inspect.signature(attest_verifier_build_from_verified_ir_v1).parameters; assert "toolchain_digest" not in inspect.signature(attest_builder_observation_v1).parameters
def test_provider_verifier_requires_current_reproducibility_gate_before_callback():
    txid,receipt,envelope=effect_chain(); x=admitted(); calls=[]; k=provider_kwargs(x,txid,receipt,envelope)
    native=verify_provider_native_response_v1(**k,verifier=lambda raw:calls.append(1) or verifier_for(txid)(raw))
    assert calls==[1]; assert native.reproducibility_receipt_digest==x['repro'].receipt_digest; assert native.builder_a_trust_anchor_generation==1
def test_newer_builder_generation_rejects_old_provider_gate_before_callback():
    txid,receipt,envelope=effect_chain(); x=admitted(); newer=seal_trust_anchor_manifest_v1(anchor_id=x['manifest_a'].anchor_id,generation=2,abi=x['attabi_a'],allowed_trust_root_ids=("root-a",),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=x['root_key_a']); x['generation_state_a'].observe(newer,root_signing_key=x['root_key_a'],abi=x['attabi_a'],current_epoch=71); calls=[]; k=provider_kwargs(x,txid,receipt,envelope)
    with pytest.raises(ValueError,match="current observed generation"): verify_provider_native_response_v1(**k,verifier=lambda raw:calls.append(1) or verifier_for(txid)(raw))
    assert calls==[]
def test_pi_profile_cannot_bypass_current_reproducible_admission():
    txid,receipt,envelope=effect_chain(); x=admitted(); native=verify_pi_native_payment_response_v1(adapter_abi=x['abi'],runtime_admission=x['base'],reproducible_admission=x['gate'],reproducibility_receipt=x['repro'],reproducibility_key=x['rkey'],builder_a_generation_state=x['generation_state_a'],builder_b_generation_state=x['generation_state_b'],provenance=x['provenance'],verifier_artifact_bytes=x['artifact'],build_provenance_key=x['bk'],runtime_admission_key=x['rak'],reproducible_admission_key=x['gate_key'],effect_envelope=envelope,effect_receipt=receipt,effect_result_txid_bytes=txid,raw_pi_response_bytes=b"raw",observed_epoch=71,verifier=verifier_for(txid),provider_native_verifier_key=b"n"*32); assert native.provider_id=="pi"
