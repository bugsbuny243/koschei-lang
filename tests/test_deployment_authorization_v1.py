from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac
import json

from koschei.deployment_authorization_v1 import (
    DeploymentAuthorization,
    canonical_deployment_authorization_payload,
    deployment_authorization_digest,
    redeem_deployment_authorization,
)
from koschei.trust_plane_v1 import (
    StaticCapabilityRequest,
    TrustArtifactManifest,
    build_local_policy,
)


TEST_SIGNING_KEY = b"deployment-authorization-test-key-32-bytes!!"


def digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fixture():
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read"],
    )
    grants = (
        ("env", "KOSCHEI_PUBLIC_", False),
        ("net", "https://api.example", False),
    )
    capabilities = ("env.read", "net.io")
    request_payload = {
        "schema_version": "koschei.static-capability-request.v1",
        "capabilities": list(capabilities),
        "grants": [
            {"domain": domain, "scope": scope, "read_only": read_only}
            for domain, scope, read_only in grants
        ],
    }
    request = StaticCapabilityRequest(
        capabilities=capabilities,
        grants=grants,
        request_digest=digest(request_payload),
    )

    artifact_sha = hashlib.sha256(b"artifact").hexdigest()
    build_digest = hashlib.sha256(b"build-manifest").hexdigest()
    release_digest = hashlib.sha256(b"release-proof").hexdigest()
    artifact_payload = {
        "schema_version": "koschei.trust-artifact-manifest.v1",
        "artifact_sha256": artifact_sha,
        "build_manifest_digest": build_digest,
        "release_proof_digest": release_digest,
        "policy_hash": policy.policy_hash,
        "capability_request_digest": request.request_digest,
        "requested_capabilities": list(request.capabilities),
    }
    artifact = TrustArtifactManifest(
        artifact_sha256=artifact_sha,
        build_manifest_digest=build_digest,
        release_proof_digest=release_digest,
        policy_hash=policy.policy_hash,
        capability_request_digest=request.request_digest,
        requested_capabilities=request.capabilities,
        manifest_digest=digest(artifact_payload),
    )
    authorization = DeploymentAuthorization(
        authorization_id="deploy-auth-0000000001",
        operation="deploy",
        environment="production",
        artifact_sha256=artifact.artifact_sha256,
        trust_manifest_digest=artifact.manifest_digest,
        policy_hash=policy.policy_hash,
        capability_request_digest=request.request_digest,
        not_before_epoch=1_000,
        expires_after_epoch=1_100,
        nonce="nonce-0000000000000001",
    )
    return policy, request, artifact, authorization


def sign(authorization: DeploymentAuthorization) -> bytes:
    return hmac.new(
        TEST_SIGNING_KEY,
        canonical_deployment_authorization_payload(authorization),
        hashlib.sha256,
    ).digest()


def verifier(payload: bytes, signature: bytes) -> bool:
    expected = hmac.new(TEST_SIGNING_KEY, payload, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


class AtomicRedeemer:
    def __init__(self):
        self.claims: dict[str, str] = {}

    def __call__(self, authorization_id: str, authorization_digest: str) -> bool:
        if authorization_id in self.claims:
            return False
        self.claims[authorization_id] = authorization_digest
        return True


def redeem(
    authorization,
    *,
    now=1_050,
    policy=None,
    request=None,
    artifact=None,
    operation="deploy",
    environment="production",
    redeemer=None,
    signature=None,
):
    base_policy, base_request, base_artifact, _ = fixture()
    policy = policy or base_policy
    request = request or base_request
    artifact = artifact or base_artifact
    redeemer = redeemer or AtomicRedeemer()
    signature = sign(authorization) if signature is None else signature
    return redeem_deployment_authorization(
        authorization,
        signature=signature,
        signature_verifier=verifier,
        atomic_redeemer=redeemer,
        current_epoch=now,
        expected_operation=operation,
        expected_environment=environment,
        artifact_manifest=artifact,
        local_policy=policy,
        capability_request=request,
    )


def test_exact_signed_authorization_redeems_once_as_evidence():
    policy, request, artifact, authorization = fixture()
    redeemer = AtomicRedeemer()
    signature = sign(authorization)

    first = redeem_deployment_authorization(
        authorization,
        signature=signature,
        signature_verifier=verifier,
        atomic_redeemer=redeemer,
        current_epoch=1_050,
        expected_operation="deploy",
        expected_environment="production",
        artifact_manifest=artifact,
        local_policy=policy,
        capability_request=request,
    )
    second = redeem_deployment_authorization(
        authorization,
        signature=signature,
        signature_verifier=verifier,
        atomic_redeemer=redeemer,
        current_epoch=1_050,
        expected_operation="deploy",
        expected_environment="production",
        artifact_manifest=artifact,
        local_policy=policy,
        capability_request=request,
    )

    assert first is not None
    assert second is None
    assert first.authorization_id == authorization.authorization_id
    assert first.operation == "deploy"
    assert first.redeemed_at_epoch == 1_050
    assert first.authorization_digest == deployment_authorization_digest(authorization)
    assert len(first.redemption_digest) == 64
    assert not hasattr(first, "spawn")
    assert not hasattr(first, "execute")
    assert redeemer.claims[authorization.authorization_id] == first.authorization_digest


def test_invalid_signature_does_not_consume_authorization():
    policy, request, artifact, authorization = fixture()
    redeemer = AtomicRedeemer()
    result = redeem_deployment_authorization(
        authorization,
        signature=b"attacker-signature",
        signature_verifier=verifier,
        atomic_redeemer=redeemer,
        current_epoch=1_050,
        expected_operation="deploy",
        expected_environment="production",
        artifact_manifest=artifact,
        local_policy=policy,
        capability_request=request,
    )
    assert result is None
    assert redeemer.claims == {}


def test_authorization_is_not_valid_before_window():
    _, _, _, authorization = fixture()
    assert redeem(authorization, now=999) is None


def test_authorization_expires_without_expiring_artifact_identity():
    policy, request, artifact, authorization = fixture()
    assert redeem(
        authorization,
        now=1_101,
        policy=policy,
        request=request,
        artifact=artifact,
    ) is None
    assert artifact.artifact_sha256 == authorization.artifact_sha256
    assert artifact.manifest_digest == authorization.trust_manifest_digest


def test_operation_swap_is_denied():
    _, _, _, authorization = fixture()
    assert redeem(authorization, operation="launch") is None


def test_environment_swap_is_denied():
    _, _, _, authorization = fixture()
    assert redeem(authorization, environment="staging") is None


def test_policy_swap_is_denied():
    _, _, _, authorization = fixture()
    swapped_policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io"],
    )
    assert redeem(authorization, policy=swapped_policy) is None


def test_forged_policy_object_is_denied():
    policy, _, _, authorization = fixture()
    forged = replace(policy, environment="staging")
    assert redeem(authorization, policy=forged) is None


def test_artifact_swap_is_denied():
    _, _, artifact, authorization = fixture()
    swapped = replace(
        artifact,
        artifact_sha256=hashlib.sha256(b"attacker-artifact").hexdigest(),
    )
    assert redeem(authorization, artifact=swapped) is None


def test_forged_manifest_digest_is_denied_before_redemption():
    _, _, artifact, authorization = fixture()
    forged = replace(
        artifact,
        manifest_digest=hashlib.sha256(b"forged-manifest").hexdigest(),
    )
    redeemer = AtomicRedeemer()
    assert redeem(authorization, artifact=forged, redeemer=redeemer) is None
    assert redeemer.claims == {}


def test_trust_manifest_swap_is_denied():
    _, _, artifact, authorization = fixture()
    swapped = replace(
        artifact,
        manifest_digest=hashlib.sha256(b"attacker-trust-manifest").hexdigest(),
    )
    assert redeem(authorization, artifact=swapped) is None


def test_static_capability_request_swap_is_denied():
    _, request, _, authorization = fixture()
    swapped = replace(
        request,
        request_digest=hashlib.sha256(b"attacker-capability-request").hexdigest(),
    )
    assert redeem(authorization, request=swapped) is None


def test_forged_static_request_contents_are_denied_before_redemption():
    _, request, _, authorization = fixture()
    forged = replace(request, capabilities=("env.read", "net.io", "process.exec"))
    redeemer = AtomicRedeemer()
    assert redeem(authorization, request=forged, redeemer=redeemer) is None
    assert redeemer.claims == {}


def test_signed_payload_mutation_is_denied():
    _, _, _, authorization = fixture()
    signature = sign(authorization)
    mutated = replace(authorization, expires_after_epoch=9_999)
    assert redeem(mutated, signature=signature) is None


def test_redeemer_is_required_for_redemption():
    policy, request, artifact, authorization = fixture()
    assert redeem_deployment_authorization(
        authorization,
        signature=sign(authorization),
        signature_verifier=verifier,
        atomic_redeemer=None,  # type: ignore[arg-type]
        current_epoch=1_050,
        expected_operation="deploy",
        expected_environment="production",
        artifact_manifest=artifact,
        local_policy=policy,
        capability_request=request,
    ) is None
