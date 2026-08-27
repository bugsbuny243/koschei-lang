from dataclasses import replace
import pytest

from koschei.builder_environment_attestation_v1 import (
    attest_builder_environment_v1, measure_builder_environment_v1, measure_builder_workload_v1,
)
from koschei.remote_attestation_evidence_v1 import (
    RemoteAttestationEvidenceV1Error, attest_remote_environment_evidence_v1,
)


def fixture():
    env=b"env-a"; workload=b"builder-workload-a"; raw=b"opaque-attestation-evidence-a"
    rvk=b"r"*32; eak=b"e"*32
    remote=attest_remote_environment_evidence_v1(
        provider_id="generic-tee", trust_root_id="root-a", raw_evidence_bytes=raw,
        environment_digest=measure_builder_environment_v1(env),
        workload_digest=measure_builder_workload_v1(workload),
        observed_epoch=10, expires_before_epoch=12,
        remote_attestation_verifier_key=rvk,
    )
    local=attest_builder_environment_v1(
        builder_id="builder-a", environment_id="env-a", environment_bytes=env,
        workload_bytes=workload, attestation_authority_id="koschei-builder-attestor",
        environment_attestation_key=eak, remote_evidence=remote,
        raw_remote_evidence_bytes=raw, remote_attestation_verifier_key=rvk,
    )
    return locals()


def test_remote_evidence_binds_environment_workload_root_and_freshness():
    x=fixture()
    x["remote"].assert_authenticated(remote_attestation_verifier_key=x["rvk"],raw_evidence_bytes=x["raw"],current_epoch=11)
    x["local"].assert_authenticated(environment_attestation_key=x["eak"],environment_bytes=x["env"],workload_bytes=x["workload"],remote_evidence=x["remote"],raw_remote_evidence_bytes=x["raw"],remote_attestation_verifier_key=x["rvk"],current_epoch=11)
    assert x["local"].trust_root_id=="root-a"
    assert x["local"].remote_attestation_evidence_digest==x["remote"].evidence_digest


def test_raw_remote_evidence_tamper_is_rejected():
    x=fixture()
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="raw evidence mismatch"):
        x["remote"].assert_authenticated(remote_attestation_verifier_key=x["rvk"],raw_evidence_bytes=b"other",current_epoch=10)


def test_stale_remote_evidence_is_rejected():
    x=fixture()
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="stale"):
        x["remote"].assert_authenticated(remote_attestation_verifier_key=x["rvk"],raw_evidence_bytes=x["raw"],current_epoch=12)


def test_trust_root_relabel_is_rejected():
    x=fixture(); forged=replace(x["remote"],trust_root_id="root-b")
    with pytest.raises(RemoteAttestationEvidenceV1Error,match="authentication failed"):
        forged.assert_authenticated(remote_attestation_verifier_key=x["rvk"],raw_evidence_bytes=x["raw"],current_epoch=10)
