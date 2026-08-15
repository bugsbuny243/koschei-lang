"""Koschei Deployment Authorization v1.

This layer authorizes *when and where* an already-identified Trust Plane artifact
may be launched or deployed. Artifact identity remains long-lived evidence;
deployment authorization is a separate, externally signed object.

Production signing is deliberately external. This module never stores or derives
a deployment signing key. Successful redemption produces evidence of one atomic
single-use claim; that evidence is deliberately not executable authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable

from .trust_plane_v1 import (
    LocalPolicy,
    StaticCapabilityRequest,
    TrustArtifactManifest,
    TrustPlaneError,
    _validate_artifact_manifest,
    _validate_capability_request,
    _validate_policy,
)

_SCHEMA = "koschei.deployment-authorization.v1"
_REDEMPTION_SCHEMA = "koschei.deployment-authorization-redemption.v1"
_ALLOWED_OPERATIONS = frozenset({"launch", "deploy"})


class DeploymentAuthorizationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentAuthorization:
    authorization_id: str
    operation: str
    environment: str
    artifact_sha256: str
    trust_manifest_digest: str
    policy_hash: str
    capability_request_digest: str
    not_before_epoch: int
    expires_after_epoch: int
    nonce: str


@dataclass(frozen=True, slots=True)
class RedeemedAuthorization:
    authorization_id: str
    operation: str
    environment: str
    authorization_digest: str
    artifact_sha256: str
    trust_manifest_digest: str
    policy_hash: str
    capability_request_digest: str
    redeemed_at_epoch: int
    redemption_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _REDEMPTION_SCHEMA,
            "authorization_id": self.authorization_id,
            "operation": self.operation,
            "environment": self.environment,
            "authorization_digest": self.authorization_digest,
            "artifact_sha256": self.artifact_sha256,
            "trust_manifest_digest": self.trust_manifest_digest,
            "policy_hash": self.policy_hash,
            "capability_request_digest": self.capability_request_digest,
            "redeemed_at_epoch": self.redeemed_at_epoch,
            "redemption_digest": self.redemption_digest,
        }


def canonical_deployment_authorization_payload(
    authorization: DeploymentAuthorization,
) -> bytes:
    if not isinstance(authorization, DeploymentAuthorization):
        raise DeploymentAuthorizationError(
            "authorization must be DeploymentAuthorization"
        )
    operation = _text(authorization.operation, "operation")
    if operation not in _ALLOWED_OPERATIONS:
        raise DeploymentAuthorizationError("operation must be launch or deploy")
    start = _epoch(authorization.not_before_epoch, "not_before_epoch")
    end = _epoch(authorization.expires_after_epoch, "expires_after_epoch")
    if end < start:
        raise DeploymentAuthorizationError(
            "authorization expiry cannot precede start"
        )
    nonce = _text(authorization.nonce, "nonce")
    if len(nonce) < 16:
        raise DeploymentAuthorizationError("nonce must contain at least 16 characters")

    payload = {
        "schema_version": _SCHEMA,
        "authorization_id": _text(authorization.authorization_id, "authorization_id"),
        "operation": operation,
        "environment": _text(authorization.environment, "environment"),
        "artifact_sha256": _hex64(authorization.artifact_sha256, "artifact_sha256"),
        "trust_manifest_digest": _hex64(
            authorization.trust_manifest_digest, "trust_manifest_digest"
        ),
        "policy_hash": _hex64(authorization.policy_hash, "policy_hash"),
        "capability_request_digest": _hex64(
            authorization.capability_request_digest, "capability_request_digest"
        ),
        "not_before_epoch": start,
        "expires_after_epoch": end,
        "nonce": nonce,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def deployment_authorization_digest(
    authorization: DeploymentAuthorization,
) -> str:
    return hashlib.sha256(
        canonical_deployment_authorization_payload(authorization)
    ).hexdigest()


def redeem_deployment_authorization(
    authorization: DeploymentAuthorization,
    *,
    signature: bytes,
    signature_verifier: Callable[[bytes, bytes], bool],
    atomic_redeemer: Callable[[str, str], bool],
    current_epoch: int,
    expected_operation: str,
    expected_environment: str,
    artifact_manifest: TrustArtifactManifest,
    local_policy: LocalPolicy,
    capability_request: StaticCapabilityRequest,
) -> RedeemedAuthorization | None:
    """Verify and atomically consume one authorization, returning evidence only."""

    try:
        if not isinstance(signature, bytes) or not signature:
            return None
        if not callable(signature_verifier) or not callable(atomic_redeemer):
            return None

        # Evidence objects are authority-adjacent inputs. Revalidate their own
        # canonical identities here instead of trusting dataclass construction.
        _validate_policy(local_policy)
        _validate_capability_request(capability_request)
        _validate_artifact_manifest(artifact_manifest)

        payload = canonical_deployment_authorization_payload(authorization)
        if not signature_verifier(payload, signature):
            return None

        now = _epoch(current_epoch, "current_epoch")
        operation = _text(expected_operation, "expected_operation")
        if operation not in _ALLOWED_OPERATIONS:
            return None
        environment = _text(expected_environment, "expected_environment")

        if authorization.operation != operation:
            return None
        if authorization.environment != environment:
            return None
        if local_policy.environment != environment:
            return None
        if authorization.policy_hash != local_policy.policy_hash:
            return None
        if authorization.artifact_sha256 != artifact_manifest.artifact_sha256:
            return None
        if authorization.trust_manifest_digest != artifact_manifest.manifest_digest:
            return None
        if authorization.capability_request_digest != capability_request.request_digest:
            return None
        if artifact_manifest.capability_request_digest != capability_request.request_digest:
            return None
        if artifact_manifest.requested_capabilities != capability_request.capabilities:
            return None
        if artifact_manifest.policy_hash != local_policy.policy_hash:
            return None
        if now < authorization.not_before_epoch or now > authorization.expires_after_epoch:
            return None

        requested = set(capability_request.capabilities)
        allowed = set(local_policy.allowed_capabilities)
        if not requested.issubset(allowed):
            return None

        authorization_digest = hashlib.sha256(payload).hexdigest()
        if not atomic_redeemer(authorization.authorization_id, authorization_digest):
            return None

        redemption_payload = {
            "schema_version": _REDEMPTION_SCHEMA,
            "authorization_id": authorization.authorization_id,
            "operation": authorization.operation,
            "environment": authorization.environment,
            "authorization_digest": authorization_digest,
            "artifact_sha256": authorization.artifact_sha256,
            "trust_manifest_digest": authorization.trust_manifest_digest,
            "policy_hash": authorization.policy_hash,
            "capability_request_digest": authorization.capability_request_digest,
            "redeemed_at_epoch": now,
        }
        return RedeemedAuthorization(
            authorization_id=authorization.authorization_id,
            operation=authorization.operation,
            environment=authorization.environment,
            authorization_digest=authorization_digest,
            artifact_sha256=authorization.artifact_sha256,
            trust_manifest_digest=authorization.trust_manifest_digest,
            policy_hash=authorization.policy_hash,
            capability_request_digest=authorization.capability_request_digest,
            redeemed_at_epoch=now,
            redemption_digest=_digest(redemption_payload),
        )
    except (
        DeploymentAuthorizationError,
        TrustPlaneError,
        TypeError,
        ValueError,
    ):
        return None


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentAuthorizationError(f"{field} must be non-empty text")
    return value.strip()


def _hex64(value: object, field: str) -> str:
    text = _text(value, field).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise DeploymentAuthorizationError(f"{field} must be a SHA-256 digest")
    return text


def _epoch(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DeploymentAuthorizationError(
            f"{field} must be a non-negative integer"
        )
    return value


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
