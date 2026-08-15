from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac

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


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def fixture():
    policy = build_local_policy(
        "production",
        allowed_capabilities=["net.io", "env.read"],
    )
    request = StaticCapabilityRequest(
        capabilities=("env.read", "net.io"),
        grants=(
            ("env", "KOSCHEI_PUBLIC_", False),
            ("net", "https://api.example", False),
        ),
        request_digest=digest("static-capability-request"),
    )
    artifact = TrustArtifactManifest(
        artifact_sha256=digest("artifact"),
        build_manifest_digest=digest("build-manifest"),
        release_proof_digest=digest("release-proof"),
        policy_hash=policy.policy_hash,
        capability_request_digest=request.request_digest,
        requested_capabilities=request.capabilities,
        manifest_digest=digest("trust-artifact-manifest"),
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


def test_artifact_swap_is_denied():
    _, _, artifact, authorization = fixture()
    swapped = replace(artifact, artifact_sha256=digest("attacker-artifact"))
    assert redeem(authorization, artifact=swapped) is None


def test_trust_manifest_swap_is_denied():
    _, _, artifact, authorization = fixture()
    swapped = replace(artifact, manifest_digest=digest("attacker-trust-manifest"))
    assert redeem(authorization, artifact=swapped) is None


def test_static_capability_request_swap_is_denied():
    _, request, _, authorization = fixture()
    swapped = replace(request, request_digest=digest("attacker-capability-request"))
    assert redeem(authorization, request=swapped) is None


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
