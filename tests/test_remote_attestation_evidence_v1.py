from dataclasses import replace
import pytest
from koschei.attestation_verifier_abi_v1 import seal_attestation_verifier_abi_v1
from koschei.builder_environment_attestation_v1 import attest_builder_environment_v1
from koschei.remote_attestation_evidence_v1 import RemoteAttestationEvidenceV1Error,RemoteAttestationVerificationResultV1,verify_remote_attestation_with_abi_v1

def fixture():
    env=b"env-a"; workload=b"builder-workload-a"; raw=b"opaque-attestation-evidence-a"; verifier_artifact=b"compiled-attestation-verifier-v1"; rvk=b"r"*32; eak=b"e"*32
    abi=seal_attestation_verifier_abi_v1(provider_id="generic-tee",evidence_format_id="opaque-test-quote",schema_version="v1",verifier_artifact_bytes=verifier_artifact)
    remote=verify_remote_attestation_with_abi_v1(abi=abi,verifier_artifact_bytes=verifier_artifact,raw_evidence_bytes=raw,current_epoch=10,verifier=lambda _:RemoteAttestationVerificationResultV1("root-a",env,workload,10,12),remote_attestation_verifier_key=rvk)
    local=attest_builder_environment_v1(builder_id="builder-a",environment_id="env-a",environment_bytes=env,workload_bytes=workload,attestation_authority_id="koschei-builder-attestor",environment_attestation_key=eak,remote_evidence=remote,raw_remote_evidence_bytes=raw,remote_attestation_verifier_key=rvk)
    return locals()
def test_remote_evidence_binds_abi_artifact_environment_root_and_freshness():
    x=fixture(); x['remote'].assert_authenticated(remote_attestation_verifier_key=x['rvk'],raw_evidence_bytes=x['raw'],current_epoch=11); assert x['remote'].attestation_verifier_abi_digest==x['abi'].abi_digest; assert x['local'].trust_root_id=='root-a'
def test_wrong_verifier_artifact_rejects_before_callback():
    x=fixture(); calls=[]
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="artifact differs"):
        verify_remote_attestation_with_abi_v1(abi=x['abi'],verifier_artifact_bytes=b"malicious",raw_evidence_bytes=x['raw'],current_epoch=10,verifier=lambda _:calls.append(1),remote_attestation_verifier_key=x['rvk'])
    assert calls==[]
def test_raw_remote_evidence_tamper_is_rejected():
    x=fixture()
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="raw evidence mismatch"): x['remote'].assert_authenticated(remote_attestation_verifier_key=x['rvk'],raw_evidence_bytes=b"other",current_epoch=10)
def test_stale_remote_evidence_is_rejected():
    x=fixture()
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="stale"): x['remote'].assert_authenticated(remote_attestation_verifier_key=x['rvk'],raw_evidence_bytes=x['raw'],current_epoch=12)
def test_trust_root_relabel_is_rejected():
    x=fixture(); forged=replace(x['remote'],trust_root_id="root-b")
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="authentication failed"): forged.assert_authenticated(remote_attestation_verifier_key=x['rvk'],raw_evidence_bytes=x['raw'],current_epoch=10)
