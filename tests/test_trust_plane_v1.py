from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.build_manifest import NativeBuildManifest
from koschei.capabilities import DYNAMIC, Grant, Manifest
from koschei.release_proof import ReleaseProof
from koschei.trust_plane_v1 import (
    StaticCapabilityRequest,
    TrustPlaneError,
    build_local_policy,
    build_static_capability_request,
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


def capability_manifest(*grants: tuple[str, str, bool]) -> Manifest:
    location = SourceLocation(1, 1)
    return Manifest(
        grants=[
            Grant(domain=domain, scope=scope, read_only=read_only, location=location)
            for domain, scope, read_only in grants
        ]
    )


def make_request(*grants: tuple[str, str, bool]):
    return build_static_capability_request(capability_manifest(*grants))


def test_exact_artifact_static_request_and_policy_are_allowed(tmp_path):
    artifact_bytes, build, proof = build_fixture()
    artifact = tmp_path / "service.bin"
    artifact.write_bytes(artifact_bytes)
    request = make_request(
        ("net", "https://api.example", False),
        ("env", "KOSCHEI_PUBLIC_", False),
    )
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read"],
    )
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
        artifact=artifact,
    )

    assert decision.allowed is True
    assert decision.code == "KS1950"
    assert decision.effective_capabilities == ("env.read", "net.io")
    assert decision.capability_request_digest == request.request_digest
    assert len(decision.decision_digest) == 64


def test_policy_and_static_request_hashes_are_order_independent():
    first_policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read", "disk.read"],
    )
    second_policy = build_local_policy(
        "production",
        allowed_capabilities=["disk.read", "net.io", "env.read"],
    )
    assert first_policy.policy_hash == second_policy.policy_hash

    left = make_request(
        ("net", "https://api.example", False),
        ("disk", "/srv/app", True),
    )
    right = make_request(
        ("disk", "/srv/app", True),
        ("net", "https://api.example", False),
    )
    assert left.request_digest == right.request_digest
    assert left.capabilities == right.capabilities == ("disk.read", "net.io")


def test_writable_disk_grant_requests_read_and_write_authority():
    request = make_request(("disk", "/srv/app", False))
    assert request.capabilities == ("disk.read", "disk.write")


def test_dynamic_source_scope_is_rejected_before_launch():
    manifest = capability_manifest(("net", DYNAMIC, False))
    with pytest.raises(TrustPlaneError) as error:
        build_static_capability_request(manifest)
    assert error.value.code == "KS1958"


def test_policy_capability_escalation_is_denied():
    _, build, proof = build_fixture()
    request = make_request(("process", "/usr/bin/worker", False))
    policy = build_local_policy("production", allowed_capabilities=["net.io"])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
    )
    assert decision.allowed is False
    assert decision.code == "KS1956"
    assert decision.effective_capabilities == ()


def test_manifest_cannot_request_more_than_static_source_analysis():
    _, build, proof = build_fixture()
    request = make_request(("net", "https://api.example", False))
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "process.exec"],
    )
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )
    payload = manifest.to_dict()
    payload["requested_capabilities"] = ["net.io", "process.exec"]
    unsigned = dict(payload)
    unsigned.pop("manifest_digest")
    forged = replace(
        manifest,
        requested_capabilities=("net.io", "process.exec"),
        manifest_digest=digest(unsigned),
    )

    decision = evaluate_launch(
        forged,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
    )
    assert decision.allowed is False
    assert decision.code == "KS1959"
    assert decision.effective_capabilities == ()


def test_privileged_launcher_capability_cannot_be_forged_as_source_request():
    _, build, proof = build_fixture()
    policy = build_local_policy("production", allowed_capabilities=["secret.use"])
    payload = {
        "schema_version": "koschei.static-capability-request.v1",
        "capabilities": ["secret.use"],
        "grants": [],
    }
    forged_request = StaticCapabilityRequest(
        capabilities=("secret.use",),
        grants=(),
        request_digest=digest(payload),
    )
    empty_request = make_request()
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        empty_request,
        policy_hash=policy.policy_hash,
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=forged_request,
        build=build,
        release_proof=proof,
    )
    assert decision.allowed is False
    assert decision.code == "KS1951"
    assert decision.effective_capabilities == ()


def test_artifact_byte_swap_is_denied(tmp_path):
    artifact_bytes, build, proof = build_fixture()
    artifact = tmp_path / "service.bin"
    artifact.write_bytes(artifact_bytes + b"-attacker-change")
    request = make_request()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
        artifact=artifact,
    )
    assert decision.allowed is False
    assert decision.code == "KS1957"


def test_release_proof_swap_is_denied():
    _, build, proof = build_fixture()
    request = make_request()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )
    swapped = replace(proof, proof_digest="a" * 64)

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=swapped,
    )
    assert decision.allowed is False
    assert decision.effective_capabilities == ()


def test_forged_release_proof_cannot_grant_production_authority():
    _, build, proof = build_fixture()
    request = make_request()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    payload = proof.to_dict()
    payload["production_integration_allowed"] = True
    unsigned = dict(payload)
    unsigned.pop("proof_digest")
    forged = replace(
        proof,
        production_integration_allowed=True,
        proof_digest=digest(unsigned),
    )
    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=forged,
    )
    assert decision.allowed is False
    assert decision.code == "KS1951"


def test_unknown_policy_capability_is_rejected():
    with pytest.raises(TrustPlaneError) as error:
        build_local_policy(
            "production",
            allowed_capabilities=["root.everything"],
        )
    assert error.value.code == "KS1951"


def test_same_inputs_produce_same_decision_digest():
    _, build, proof = build_fixture()
    request = make_request(("env", "KOSCHEI_PUBLIC_", False))
    policy = build_local_policy("production", allowed_capabilities=["env.read"])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    first = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
    )
    second = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
    )
    assert first.to_dict() == second.to_dict()


def test_release_proof_is_evidence_not_ambient_deploy_authority():
    _, build, proof = build_fixture()
    request = make_request()
    policy = build_local_policy("production", allowed_capabilities=[])
    manifest = build_trust_artifact_manifest(
        build,
        proof,
        request,
        policy_hash=policy.policy_hash,
    )

    decision = evaluate_launch(
        manifest,
        local_policy=policy,
        capability_request=request,
        build=build,
        release_proof=proof,
    )
    assert proof.production_integration_allowed is False
    assert decision.allowed is True
    assert decision.effective_capabilities == ()
