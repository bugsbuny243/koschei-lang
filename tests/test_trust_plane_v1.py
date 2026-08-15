from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from koschei.build_manifest import NativeBuildManifest
from koschei.release_proof import ReleaseProof
from koschei.trust_plane_v1 import (
    TrustPlaneError,
    build_local_policy,
    build_trust_artifact_manifest,
    evaluate_launch,
)


def digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_fixture(artifact_bytes: bytes = b"koschei-trusted-artifact-v1"):
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    build_payload = {
        "schema_version": "koschei.native-build-manifest.v1",
        "artifact_name": "service.bin",
        "artifact_size": len(artifact_bytes),
        "artifact_sha256": artifact_sha256,
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
        artifact_sha256=artifact_sha256,
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
        "release_artifact_sha256": build.artifact_sha256,
        "witness_artifact_sha256": build.artifact_sha256,
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
        release_artifact_sha256=build.artifact_sha256,
        witness_artifact_sha256=build.artifact_sha256,
        reproducibility_report_digest="4" * 64,
        shared_input_digest="5" * 64,
        byte_reproducible=True,
        owner_approval_required=True,
        automatic_publish_allowed=False,
        package_registry_write_allowed=False,
        production_integration_allowed=False,
        proof_digest=digest(proof_payload),
    )
    return artifact_bytes, build, proof


def test_exact_artifact_and_policy_are_allowed(tmp_path):
    artifact_bytes, build, proof = build_fixture()
    artifact = tmp_path / "service.bin"
    artifact.write_bytes(artifact_bytes)
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read"],
    )
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=policy.policy_hash,
        requested_capabilities=["env.read", "net.io"],
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=proof,
        artifact=artifact,
    )

    assert decision.allowed is True
    assert decision.code == "KS1950"
    assert decision.effective_capabilities == ("env.read", "net.io")
    assert len(decision.decision_digest) == 64


def test_policy_and_manifest_hashes_are_order_independent():
    _, build, proof = build_fixture()
    first = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read", "disk.read"],
    )
    second = build_local_policy(
        "production",
        allowed_capabilities=["disk.read", "net.io", "env.read"],
    )
    assert first.policy_hash == second.policy_hash

    left = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=first.policy_hash,
        requested_capabilities=["net.io", "disk.read"],
    )
    right = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=first.policy_hash,
        requested_capabilities=["disk.read", "net.io"],
    )
    assert left.manifest_digest == right.manifest_digest


def test_capability_escalation_is_denied():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=["net.io"])
    wider_policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "process.exec"],
    )
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=wider_policy.policy_hash,
        requested_capabilities=["net.io", "process.exec"],
    )
    # Tampering the manifest to the narrower policy hash must not help because the
    # manifest digest also binds the original policy hash.
    tampered = replace(manifest, policy_hash=policy.policy_hash)

    decision = evaluate_launch(
        tampered,
        local_policy=policy,
        build=build,
        release_proof=proof,
    )
    assert decision.allowed is False
    assert decision.effective_capabilities == ()
    assert decision.code == "KS1951"


def test_requested_capability_not_in_local_policy_is_denied():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=["net.io"])
    broad_policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "process.exec"],
    )
    broad_manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=broad_policy.policy_hash,
        requested_capabilities=["net.io", "process.exec"],
    )
    # Construct a valid manifest bound to the narrow policy but requesting more.
    payload = broad_manifest.to_dict()
    payload["policy_hash"] = policy.policy_hash
    unsigned = dict(payload)
    unsigned.pop("manifest_digest")
    forged = replace(
        broad_manifest,
        policy_hash=policy.policy_hash,
        manifest_digest=digest(unsigned),
    )

    decision = evaluate_launch(
        forged,
        local_policy=policy,
        build=build,
        release_proof=proof,
    )
    assert decision.allowed is False
    assert decision.code == "KS1956"
    assert decision.effective_capabilities == ()


def test_artifact_byte_swap_is_denied(tmp_path):
    artifact_bytes, build, proof = build_fixture()
    artifact = tmp_path / "service.bin"
    artifact.write_bytes(artifact_bytes + b"-attacker-change")
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=policy.policy_hash,
        requested_capabilities=[],
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=proof,
        artifact=artifact,
    )
    assert decision.allowed is False
    assert decision.code == "KS1957"


def test_release_proof_swap_is_denied():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=policy.policy_hash,
        requested_capabilities=[],
    )
    swapped = replace(proof, proof_digest="a" * 64)

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=swapped,
    )
    assert decision.allowed is False
    assert decision.effective_capabilities == ()


def test_unknown_capability_is_rejected_before_policy_exists():
    with pytest.raises(TrustPlaneError) as error:
        build_local_policy(
            "production",
            allowed_capabilities=["root.everything"],
        )
    assert error.value.code == "KS1951"


def test_same_inputs_produce_same_decision_digest():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=["env.read"])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=policy.policy_hash,
        requested_capabilities=["env.read"],
    )

    first = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=proof,
    )
    second = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=proof,
    )
    assert first.to_dict() == second.to_dict()


def test_release_proof_is_evidence_not_ambient_deploy_authority():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        policy_hash=policy.policy_hash,
        requested_capabilities=[],
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        build=build,
        release_proof=proof,
    )
    assert proof.production_integration_allowed is False
    assert decision.allowed is True
    assert decision.effective_capabilities == ()
