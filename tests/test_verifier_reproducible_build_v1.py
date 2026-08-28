from dataclasses import replace
import hashlib
import pytest
from koschei.attestation_verifier_abi_v1 import seal_attestation_verifier_abi_v1
from koschei.builder_environment_attestation_v1 import attest_builder_environment_v1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse
from koschei.provider_adapter_abi_v1 import seal_provider_adapter_abi_v1
from koschei.remote_attestation_evidence_v1 import RemoteAttestationVerificationResultV1,verify_remote_attestation_with_abi_v1
from koschei.toolchain_provenance_v1 import attest_toolchain_provenance_v1
from koschei.trust_anchor_admission_v1 import seal_trust_anchor_manifest_v1,admit_attestation_verifier_from_trust_anchor_v1
from koschei.verified_ir_build_input_v1 import derive_verified_ir_build_input_v1
from koschei.verifier_build_provenance_v1 import attest_verifier_build_from_verified_ir_v1,measure_verifier_artifact_v1
from koschei.verifier_reproducible_admission_v1 import VerifierReproducibleAdmissionV1Error,admit_reproducible_verifier_artifact_v1
from koschei.verifier_reproducible_build_v1 import VerifierReproducibleBuildV1Error,attest_builder_observation_v1,seal_reproducible_build_receipt_v1
SOURCE="""ka treasury;\nvor withdrawal;\nshi evidence;\nthal recovery;\nnur visibility;\n"""
def verified_world():
    mir=lower_native_sigils(parse(SOURCE)); plan=expand_native_sigil_mir(mir).library_plan
    receipts=[make_receipt(activation_step_id=s.activation_step_id,obligation=s.obligation,subsystem=s.subsystem,proof_kind=s.proof_kind,evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),success=True) for s in plan.steps]
    proof=seal_native_sigil_proof(mir,receipts); return mir,proof,derive_verified_ir_build_input_v1(mir=mir,proof=proof)
def tc(version,byte):
    artifact=("compiler-"+version).encode(); key=byte*32
    return attest_toolchain_provenance_v1(toolchain_id="koschei-compiler",toolchain_version=version,toolchain_artifact_bytes=artifact,build_profile="release",toolchain_signing_key=key),artifact,key
def env(builder,suffix,keybyte,root):
    ebytes=("env-"+suffix).encode(); wbytes=("workload-"+builder).encode(); raw=("quote-"+suffix).encode(); verifier_artifact=("attestation-verifier-"+suffix).encode(); remote_key=keybyte.upper()*32; env_key=keybyte*32; root_key=(suffix.encode()*32)[:32]; admission_key=(suffix.upper().encode()*32)[:32]
    abi=seal_attestation_verifier_abi_v1(provider_id="bootstrap-test-attestor",evidence_format_id="opaque-test-quote",schema_version="v1",verifier_artifact_bytes=verifier_artifact)
    manifest=seal_trust_anchor_manifest_v1(anchor_id="offline-root-"+suffix,abi=abi,allowed_trust_root_ids=(root,),valid_from_epoch=70,expires_before_epoch=90,root_signing_key=root_key)
    root_admission=admit_attestation_verifier_from_trust_anchor_v1(manifest=manifest,abi=abi,verifier_artifact_bytes=verifier_artifact,current_epoch=71,root_signing_key=root_key,runtime_admission_key=admission_key)
    remote=verify_remote_attestation_with_abi_v1(abi=abi,verifier_artifact_bytes=verifier_artifact,raw_evidence_bytes=raw,current_epoch=71,verifier=lambda _:RemoteAttestationVerificationResultV1(root,ebytes,wbytes,71,80),remote_attestation_verifier_key=remote_key,trust_anchor_manifest=manifest,trust_anchor_admission=root_admission,root_signing_key=root_key,trust_anchor_runtime_admission_key=admission_key)
    receipt=attest_builder_environment_v1(builder_id=builder,environment_id="environment-"+suffix,environment_bytes=ebytes,workload_bytes=wbytes,attestation_authority_id="koschei-build-attestor",environment_attestation_key=env_key,remote_evidence=remote,raw_remote_evidence_bytes=raw,remote_attestation_verifier_key=remote_key)
    return receipt,ebytes,wbytes,env_key,remote,raw,remote_key,abi,verifier_artifact,manifest,root_admission,root_key,admission_key
def chain():
    mir,proof,verified=verified_world(); artifact=b"deterministic-verifier-artifact-v1"
    akey,bkey,rkey=b"A"*32,b"B"*32,b"R"*32; bk,rk,gak=b"P"*32,b"L"*32,b"G"*32
    tc_a,tc_a_bytes,tc_a_key=tc("a",b"x"); tc_b,tc_b_bytes,tc_b_key=tc("b",b"y")
    env_a,env_a_bytes,work_a,env_a_key,remote_a,raw_a,remote_a_key,attabi_a,attart_a,manifest_a,root_admission_a,root_key_a,root_admission_key_a=env("builder-a","a",b"m","root-a")
    env_b,env_b_bytes,work_b,env_b_key,remote_b,raw_b,remote_b_key,attabi_b,attart_b,manifest_b,root_admission_b,root_key_b,root_admission_key_b=env("builder-b","b",b"n","root-b")
    obs_a=attest_builder_observation_v1(builder_id="builder-a",builder_key=akey,verified_input=verified,mir=mir,proof=proof,toolchain=tc_a,toolchain_artifact_bytes=tc_a_bytes,toolchain_signing_key=tc_a_key,environment=env_a,environment_bytes=env_a_bytes,workload_bytes=work_a,environment_attestation_key=env_a_key,remote_evidence=remote_a,raw_remote_evidence_bytes=raw_a,remote_attestation_verifier_key=remote_a_key,current_epoch=71,artifact_bytes=artifact,build_profile="release-reproducible")
    obs_b=attest_builder_observation_v1(builder_id="builder-b",builder_key=bkey,verified_input=verified,mir=mir,proof=proof,toolchain=tc_b,toolchain_artifact_bytes=tc_b_bytes,toolchain_signing_key=tc_b_key,environment=env_b,environment_bytes=env_b_bytes,workload_bytes=work_b,environment_attestation_key=env_b_key,remote_evidence=remote_b,raw_remote_evidence_bytes=raw_b,remote_attestation_verifier_key=remote_b_key,current_epoch=71,artifact_bytes=artifact,build_profile="release-reproducible")
    common=dict(reproducibility_key=rkey,builder_a_key=akey,builder_b_key=bkey,builder_a=obs_a,builder_b=obs_b,builder_a_toolchain=tc_a,builder_b_toolchain=tc_b,builder_a_toolchain_artifact_bytes=tc_a_bytes,builder_b_toolchain_artifact_bytes=tc_b_bytes,builder_a_toolchain_signing_key=tc_a_key,builder_b_toolchain_signing_key=tc_b_key,builder_a_environment=env_a,builder_b_environment=env_b,builder_a_environment_bytes=env_a_bytes,builder_b_environment_bytes=env_b_bytes,builder_a_workload_bytes=work_a,builder_b_workload_bytes=work_b,builder_a_environment_attestation_key=env_a_key,builder_b_environment_attestation_key=env_b_key,builder_a_remote_evidence=remote_a,builder_b_remote_evidence=remote_b,builder_a_raw_remote_evidence_bytes=raw_a,builder_b_raw_remote_evidence_bytes=raw_b,builder_a_remote_attestation_verifier_key=remote_a_key,builder_b_remote_attestation_verifier_key=remote_b_key,current_epoch=71,verified_input=verified,mir=mir,proof=proof,artifact_bytes=artifact)
    repro=seal_reproducible_build_receipt_v1(**common,require_distinct_trust_roots=True)
    provenance=attest_verifier_build_from_verified_ir_v1(verified_input=verified,mir=mir,proof=proof,artifact_bytes=artifact,toolchain=tc_a,toolchain_artifact_bytes=tc_a_bytes,toolchain_signing_key=tc_a_key,build_profile="release-reproducible",build_provenance_key=bk)
    abi=seal_provider_adapter_abi_v1(provider_id="pi",adapter_id="pi-verifier",schema_id="pi-payment",schema_version="v1",verifier_implementation_digest=measure_verifier_artifact_v1(artifact))
    base,gated=admit_reproducible_verifier_artifact_v1(**common,reproducible_admission_key=gak,runtime_admission_key=rk,build_provenance_key=bk,reproducibility_receipt=repro,build_toolchain=tc_a,build_toolchain_artifact_bytes=tc_a_bytes,build_toolchain_signing_key=tc_a_key,provenance=provenance,adapter_abi=abi,require_distinct_trust_roots=True)
    return locals()
def test_two_builders_require_remote_attested_distinct_environments():
    x=chain(); assert x['repro'].builder_a_remote_attestation_evidence_digest==x['remote_a'].evidence_digest; assert x['remote_a'].trust_anchor_manifest_digest==x['manifest_a'].manifest_digest
def test_same_trust_root_rejected_when_policy_requires_distinct_roots():
    x=chain(); same_root=replace(x['remote_b'],trust_root_id=x['remote_a'].trust_root_id)
    with pytest.raises(ValueError): x['env_b'].assert_authenticated(environment_attestation_key=x['env_b_key'],environment_bytes=x['env_b_bytes'],workload_bytes=x['work_b'],remote_evidence=same_root,raw_remote_evidence_bytes=x['raw_b'],remote_attestation_verifier_key=x['remote_b_key'],current_epoch=71)
def test_environment_attestation_tamper_rejects_builder_observation():
    x=chain(); forged=replace(x['env_a'],workload_digest='0'*64)
    with pytest.raises(ValueError): x['obs_a'].assert_authenticated(builder_key=x['akey'],verified_input=x['verified'],mir=x['mir'],proof=x['proof'],toolchain=x['tc_a'],toolchain_artifact_bytes=x['tc_a_bytes'],toolchain_signing_key=x['tc_a_key'],environment=forged,environment_bytes=x['env_a_bytes'],workload_bytes=x['work_a'],environment_attestation_key=x['env_a_key'],remote_evidence=x['remote_a'],raw_remote_evidence_bytes=x['raw_a'],remote_attestation_verifier_key=x['remote_a_key'],current_epoch=71,artifact_bytes=x['artifact'])
def test_reproducible_admission_tampering_is_rejected():
    x=chain(); forged=replace(x['gated'],reproducibility_receipt_digest='0'*64)
    with pytest.raises(VerifierReproducibleAdmissionV1Error): forged.assert_authenticated(reproducible_admission_key=x['gak'],base_admission=x['base'],adapter_abi=x['abi'])
