"""Commercial entitlement and artifact identity primitives for Koschei.

This module deliberately does not contain a signing private key. Production
signatures are expected to be produced by a separate licensing/distribution
service or HSM-backed signer. Client-side code only canonicalizes claims and
verifies them through an injected verifier.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable


class CommercialEntitlementError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    product: str
    version: str
    artifact_sha256: str
    policy_hash: str
    channel: str


@dataclass(frozen=True, slots=True)
class EntitlementClaims:
    customer_id: str
    edition: str
    seats: int
    features: tuple[str, ...]
    not_before_epoch: int
    expires_after_epoch: int
    artifact: ArtifactIdentity


def _nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommercialEntitlementError(f"{field} must be non-empty text")
    return value.strip()


def _hex64(value: str, field: str) -> str:
    value = _nonempty(value, field).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise CommercialEntitlementError(f"{field} must be a 32-byte hex digest")
    return value


def _epoch(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CommercialEntitlementError(f"{field} must be a non-negative integer")
    return value


def canonical_entitlement_payload(claims: EntitlementClaims) -> bytes:
    if not isinstance(claims, EntitlementClaims):
        raise CommercialEntitlementError("claims must be EntitlementClaims")
    if claims.seats < 1:
        raise CommercialEntitlementError("seats must be >= 1")
    start = _epoch(claims.not_before_epoch, "not_before_epoch")
    end = _epoch(claims.expires_after_epoch, "expires_after_epoch")
    if end < start:
        raise CommercialEntitlementError("entitlement expiry cannot precede start")
    artifact = claims.artifact
    obj = {
        "schema": "koschei/commercial-entitlement/v1",
        "customer_id": _nonempty(claims.customer_id, "customer_id"),
        "edition": _nonempty(claims.edition, "edition"),
        "seats": claims.seats,
        "features": sorted({_nonempty(item, "feature") for item in claims.features}),
        "not_before_epoch": start,
        "expires_after_epoch": end,
        "artifact": {
            "product": _nonempty(artifact.product, "product"),
            "version": _nonempty(artifact.version, "version"),
            "artifact_sha256": _hex64(artifact.artifact_sha256, "artifact_sha256"),
            "policy_hash": _hex64(artifact.policy_hash, "policy_hash"),
            "channel": _nonempty(artifact.channel, "channel"),
        },
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def entitlement_digest(claims: EntitlementClaims) -> str:
    return hashlib.sha256(canonical_entitlement_payload(claims)).hexdigest()


def verify_entitlement(*, claims: EntitlementClaims, signature: bytes, verifier: Callable[[bytes, bytes], bool], current_epoch: int, expected_artifact_sha256: str, expected_policy_hash: str, required_feature: str | None = None) -> bool:
    try:
        now = _epoch(current_epoch, "current_epoch")
        payload = canonical_entitlement_payload(claims)
        if now < claims.not_before_epoch or now > claims.expires_after_epoch:
            return False
        if claims.artifact.artifact_sha256 != _hex64(expected_artifact_sha256, "expected_artifact_sha256"):
            return False
        if claims.artifact.policy_hash != _hex64(expected_policy_hash, "expected_policy_hash"):
            return False
        if required_feature is not None and required_feature not in claims.features:
            return False
        if not isinstance(signature, bytes) or not signature:
            return False
        return bool(verifier(payload, signature))
    except (CommercialEntitlementError, TypeError, ValueError):
        return False
