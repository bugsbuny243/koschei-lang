from __future__ import annotations

import hashlib
import hmac
import json

from koschei.ast_nodes import SourceLocation
from koschei.build_manifest import NativeBuildManifest
from koschei.capabilities import Grant, Manifest
from koschei.deployment_authorization_v1 import (
    DeploymentAuthorization,
    canonical_deployment_authorization_payload,
)
from koschei.release_proof import ReleaseProof
from koschei.trust_plane_v1 import (
    build_local_policy,
    build_static_capability_request,
    build_trust_artifact_manifest,
)
from koschei.trusted_launcher_v1 import authorize_trusted_launch


TEST_KEY = b"trusted-launcher-external-verifier-test-key!!"


def digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Redeemer:
    def __init__(self):
        self.claims: dict[str, str] = {}

    def __call__(self, authorization_id: str, authorization_digest: str) -> bool:
        if authorization_id in self.claims:
            return False
        self.claims[authorization_id] = authorization_digest
        return True


def fixture(tmp_path):
    artifact_bytes = b"koschei-trusted-launcher-integration-artifact"
    artifact = tmp_path / "service.bin"
    artifact.write_bytes(artifact_bytes)
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()

    build_payload = {
        "schema_version": "koschei.native-build-manifest.v1",
        "artifact_name": "service.bin",
        "artifact_size": len(artifact_bytes),
        "artifact_sha256": artifact_sha,
        "module_lock_digest": "1" * 64,
        "mir_version": "1",
        "mir_fingerprint": "2" * 64,
        "compiler_version": "test",
        "backend": "go-native",
        "backend_toolchain": "go-test",
    }
    build = NativeBuildManifest(
        artifact_name="service.bin",
        artifact_size=len(artifact_bytes),
        artifact_sha256=artifact_sha,
        module_lock_digest="1" * 64,
        mir_version="1",
        mir_fingerprint="2" * 64,
        compiler_version="test",
        backend="go-native",
        backend_toolchain="go-test",
        manifest_digest=digest(build_payload),
    )

    proof_payload = {
        "schema_version": "koschei.release-proof.v1",
        "state": "verified_reproducible_release_candidate",
        "authority": "release_candidate_evidence_only",
        "module_lock_digest": build.module_lock_digest,
        "mir_version": build.mir_version,
        "mir_fingerprint": build.mir_fingerprint,
        "compiler_version": build.compiler_version,
        "backend": build.backend,
        "backend_toolchain": build.backend_toolchain,
        "release_manifest_digest": build.manifest_digest,
        "witness_manifest_digest": "3" * 64,
        "release_artifact_sha256": artifact_sha,
        "witness_artifact_sha256": artifact_sha,
        "reproducibility_report_digest": "4" * 64,
        "shared_input_digest": "5" * 64,
        "byte_reproducible": True,
        "owner_approval_required": True,
        "automatic_publish_allowed": False,
        "package_registry_write_allowed": False,
        "production_integration_allowed": False,
    }
    proof = ReleaseProof(
        state="verified_reproducible_release_candidate",
        authority="release_candidate_evidence_only",
        module_lock_digest=build.module_lock_digest,
        mir_version=build.mir_version,
        mir_fingerprint=build.mir_fingerprint,
        compiler_version=build.compiler_version,
        backend=build.backend,
        backend_toolchain=build.backend_toolchain,
        release_manifest_digest=build.manifest_digest,
        witness_manifest_digest="3" * 64,
        release_artifact_sha256=artifact_sha,
        witness_artifact_sha256=artifact_sha,
        reproducibility_report_digest="4" * 64,
        shared_input_digest="5" * 64,
        byte_reproducible=True,
        owner_approval_required=True,
        automatic_publish_allowed=False,
        package_registry_write_allowed=False,
        production_integration_allowed=False,
        proof_digest=digest(proof_payload),
    )

    source_manifest = Manifest(
        grants=[
            Grant(
                domain="net",
                scope="https://api.example",
                read_only=False,
                location=SourceLocation(1, 1),
            )
        ]
    )
    request = build_static_capability_request(source_manifest)
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io"],
    )
    trust_manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )
    authorization = DeploymentAuthorization(
        authorization_id="launch-auth-integration-0001",
        operation="launch",
        environment="production",
        artifact_sha256=artifact_sha,
        trust_manifest_digest=trust_manifest.manifest_digest,
        policy_hash=policy.policy_hash,
        capability_request_digest=request.request_digest,
        not_before_epoch=1_000,
        expires_after_epoch=1_100,
        nonce="launcher-nonce-00000001",
    )
    signature = hmac.new(
        TEST_KEY,
        canonical_deployment_authorization_payload(authorization),
        hashlib.sha256,
    ).digest()

    def verifier(payload: bytes, supplied: bytes) -> bool:
        expected = hmac.new(TEST_KEY, payload, hashlib.sha256).digest()
        return hmac.compare_digest(expected, supplied)

    return {
        "artifact": artifact,
        "build": build,
        "proof": proof,
        "request": request,
        "policy": policy,
        "trust_manifest": trust_manifest,
        "authorization": authorization,
        "signature": signature,
        "verifier": verifier,
    }


def authorize(values, redeemer):
    return authorize_trusted_launch(
        artifact_manifest=values["trust_manifest"],
        local_policy=values["policy"],
        capability_request=values["request"],
        build=values["build"],
        release_proof=values["proof"],
        artifact=values["artifact"],
        deployment_authorization=values["authorization"],
        authorization_signature=values["signature"],
        signature_verifier=values["verifier"],
        atomic_redeemer=redeemer,
        current_epoch=1_050,
    )


def test_full_chain_emits_bound_launch_permit(tmp_path):
    values = fixture(tmp_path)
    permit = authorize(values, Redeemer())

    assert permit is not None
    assert permit.environment == "production"
    assert permit.artifact_sha256 == values["build"].artifact_sha256
    assert permit.policy_hash == values["policy"].policy_hash
    assert permit.capability_request_digest == values["request"].request_digest
    assert permit.effective_capabilities == ("net.io",)
    assert permit.authorization_id == values["authorization"].authorization_id
    assert len(permit.permit_digest) == 64


def test_artifact_tamper_fails_before_authorization_is_consumed(tmp_path):
    values = fixture(tmp_path)
    values["artifact"].write_bytes(b"attacker replacement")
    redeemer = Redeemer()

    permit = authorize(values, redeemer)

    assert permit is None
    assert redeemer.claims == {}


def test_replay_cannot_emit_second_permit(tmp_path):
    values = fixture(tmp_path)
    redeemer = Redeemer()

    first = authorize(values, redeemer)
    second = authorize(values, redeemer)

    assert first is not None
    assert second is None


def test_bad_signature_cannot_emit_permit_or_consume_grant(tmp_path):
    values = fixture(tmp_path)
    values["signature"] = b"wrong-signature"
    redeemer = Redeemer()

    permit = authorize(values, redeemer)

    assert permit is None
    assert redeemer.claims == {}


def test_same_valid_chain_has_same_permit_identity_with_fresh_replay_store(tmp_path):
    values = fixture(tmp_path)

    first = authorize(values, Redeemer())
    second = authorize(values, Redeemer())

    assert first is not None and second is not None
    assert first.to_dict() == second.to_dict()
