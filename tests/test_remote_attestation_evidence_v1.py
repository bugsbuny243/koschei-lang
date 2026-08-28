from dataclasses import replace
import pytest
from koschei.attestation_verifier_abi_v1 import seal_attestation_verifier_abi_v1
from koschei.builder_environment_attestation_v1 import attest_builder_environment_v1
from koschei.remote_attestation_evidence_v1 import RemoteAttestationEvidenceV1Error,RemoteAttestationVerificationResultV1,verify_remote_attestation_with_abi_v1
from koschei.trust_anchor_admission_v1 import TrustAnchorAdmissionV1Error,seal_trust_anchor_manifest_v1,admit_attestation_verifier_from_trust_anchor_v1

def fixture():
    env=b"env-a"; workload=b"builder-workload-a"; raw=b"opaque-attestation-evidence-a"; verifier_artifact=b"compiled-attestation-verifier-v1"
    rvk=b"r"*32; eak=b"e"*32; root_key=b"o"*32; admission_key=b"a"*32
    abi=seal_attestation_verifier_abi_v1(provider_id="generic-tee",evidence_format_id="opaque-test-quote",schema_version="v1",verifier_artifact_bytes=verifier_artifact)
    manifest=seal_trust_anchor_manifest_v1(anchor_id="offline-root-v1",abi=abi,allowed_trust_root_ids=("root-a",),valid_from_epoch=9,expires_before_epoch=20,root_signing_key=root_key)
    root_admission=admit_attestation_verifier_from_trust_anchor_v1(manifest=manifest,abi=abi,verifier_artifact_bytes=verifier_artifact,current_epoch=10,root_signing_key=root_key,runtime_admission_key=admission_key)
    remote=verify_remote_attestation_with_abi_v1(abi=abi,verifier_artifact_bytes=verifier_artifact,raw_evidence_bytes=raw,current_epoch=10,verifier=lambda _:RemoteAttestationVerificationResultV1("root-a",env,workload,10,12),remote_attestation_verifier_key=rvk,trust_anchor_manifest=manifest,trust_anchor_admission=root_admission,root_signing_key=root_key,trust_anchor_runtime_admission_key=admission_key)
    local=attest_builder_environment_v1(builder_id="builder-a",environment_id="env-a",environment_bytes=env,workload_bytes=workload,attestation_authority_id="koschei-builder-attestor",environment_attestation_key=eak,remote_evidence=remote,raw_remote_evidence_bytes=raw,remote_attestation_verifier_key=rvk)
    return locals()

def verify_kwargs(x):
    return dict(abi=x['abi'],verifier_artifact_bytes=x['verifier_artifact'],raw_evidence_bytes=x['raw'],current_epoch=10,remote_attestation_verifier_key=x['rvk'],trust_anchor_manifest=x['manifest'],trust_anchor_admission=x['root_admission'],root_signing_key=x['root_key'],trust_anchor_runtime_admission_key=x['admission_key'])

def test_remote_evidence_binds_root_admission_abi_artifact_environment_and_freshness():
    x=fixture(); x['remote'].assert_authenticated(remote_attestation_verifier_key=x['rvk'],raw_evidence_bytes=x['raw'],current_epoch=11)
    assert x['remote'].attestation_verifier_abi_digest==x['abi'].abi_digest
    assert x['remote'].trust_anchor_manifest_digest==x['manifest'].manifest_digest
    assert x['remote'].trust_anchor_runtime_admission_digest==x['root_admission'].admission_digest
    assert x['local'].trust_root_id=='root-a'

def test_wrong_verifier_artifact_rejects_before_callback():
    x=fixture(); calls=[]; k=verify_kwargs(x); k['verifier_artifact_bytes']=b"malicious"
    with pytest.raises((RemoteAttestationEvidenceV1Error,TrustAnchorAdmissionV1Error),match="artifact"):
        verify_remote_attestation_with_abi_v1(**k,verifier=lambda _:calls.append(1))
    assert calls==[]

def test_unallowed_trust_root_is_rejected_after_verifier_result():
    x=fixture(); k=verify_kwargs(x)
    with pytest.raises(TrustAnchorAdmissionV1Error,match="not allowed"):
        verify_remote_attestation_with_abi_v1(**k,verifier=lambda _:RemoteAttestationVerificationResultV1("root-b",x['env'],x['workload'],10,12))

def test_revoked_verifier_manifest_cannot_admit_runtime():
    x=fixture(); revoked=seal_trust_anchor_manifest_v1(anchor_id="offline-root-v1",abi=x['abi'],allowed_trust_root_ids=("root-a",),valid_from_epoch=9,expires_before_epoch=20,revoked_verifier=True,root_signing_key=x['root_key'])
    with pytest.raises(TrustAnchorAdmissionV1Error,match="revoked"):
        admit_attestation_verifier_from_trust_anchor_v1(manifest=revoked,abi=x['abi'],verifier_artifact_bytes=x['verifier_artifact'],current_epoch=10,root_signing_key=x['root_key'],runtime_admission_key=x['admission_key'])

def test_expired_root_manifest_rejects_before_callback():
    x=fixture(); expired=seal_trust_anchor_manifest_v1(anchor_id="offline-root-v1",abi=x['abi'],allowed_trust_root_ids=("root-a",),valid_from_epoch=1,expires_before_epoch=10,root_signing_key=x['root_key']); calls=[]
    stale=replace(x['root_admission'],manifest_digest=expired.manifest_digest)
    with pytest.raises(TrustAnchorAdmissionV1Error,match="not live"):
        verify_remote_attestation_with_abi_v1(abi=x['abi'],verifier_artifact_bytes=x['verifier_artifact'],raw_evidence_bytes=x['raw'],current_epoch=10,verifier=lambda _:calls.append(1),remote_attestation_verifier_key=x['rvk'],trust_anchor_manifest=expired,trust_anchor_admission=stale,root_signing_key=x['root_key'],trust_anchor_runtime_admission_key=x['admission_key'])
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
