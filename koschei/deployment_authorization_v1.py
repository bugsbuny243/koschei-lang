"""Koschei Deployment Authorization v1.

This layer authorizes *when and where* an already-identified Trust Plane artifact
may be launched or deployed. Artifact identity remains long-lived evidence;
deployment authorization is a separate, externally signed object.

Production signing is deliberately external. This module never stores or derives
a deployment signing key. A successful authorization is also atomically redeemed
by the trusted state layer before authority is returned, preventing check-then-use
replay races.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable

from .trust_plane_v1 import LocalPolicy, StaticCapabilityRequest, TrustArtifactManifest

_SCHEMA = "koschei.deployment-authorization.v1"
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


def canonical_deployment_authorization_payload(
    authorization: DeploymentAuthorization,
) -> bytes:
    """Return the exact bytes an external deployment authority signs."""

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
        "authorization_id": _text(
            authorization.authorization_id,
            "authorization_id",
        ),
        "operation": operation,
        "environment": _text(authorization.environment, "environment"),
        "artifact_sha256": _hex64(
            authorization.artifact_sha256,
            "artifact_sha256",
        ),
        "trust_manifest_digest": _hex64(
            authorization.trust_manifest_digest,
            "trust_manifest_digest",
        ),
        "policy_hash": _hex64(authorization.policy_hash, "policy_hash"),
        "capability_request_digest": _hex64(
            authorization.capability_request_digest,
            "capability_request_digest",
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
) -> bool:
    """Verify and atomically consume one deployment authorization.

    ``atomic_redeemer(authorization_id, authorization_digest)`` must perform a
    single atomic claim in trusted storage and return True only for the first
    successful claim. Merely checking a consumed flag and writing later is not a
    valid implementation of this callback.
    """

    try:
        if not isinstance(signature, bytes) or not signature:
            return False
        if not callable(signature_verifier) or not callable(atomic_redeemer):
            return False

        payload = canonical_deployment_authorization_payload(authorization)
        if not signature_verifier(payload, signature):
            return False

        now = _epoch(current_epoch, "current_epoch")
        operation = _text(expected_operation, "expected_operation")
        if operation not in _ALLOWED_OPERATIONS:
            return False
        environment = _text(expected_environment, "expected_environment")

        if authorization.operation != operation:
            return False
        if authorization.environment != environment:
            return False
        if local_policy.environment != environment:
            return False
        if authorization.policy_hash != local_policy.policy_hash:
            return False
        if authorization.artifact_sha256 != artifact_manifest.artifact_sha256:
            return False
        if authorization.trust_manifest_digest != artifact_manifest.manifest_digest:
            return False
        if (
            authorization.capability_request_digest
            != capability_request.request_digest
        ):
            return False
        if (
            artifact_manifest.capability_request_digest
            != capability_request.request_digest
        ):
            return False
        if artifact_manifest.policy_hash != local_policy.policy_hash:
            return False
        if now < authorization.not_before_epoch:
            return False
        if now > authorization.expires_after_epoch:
            return False

        authorization_digest = hashlib.sha256(payload).hexdigest()
        return bool(
            atomic_redeemer(
                authorization.authorization_id,
                authorization_digest,
            )
        )
    except (DeploymentAuthorizationError, TypeError, ValueError):
        return False


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
