"""Private artifact distribution contract for Koschei commercial builds.

Client/runtime code verifies signed channel metadata, revocation snapshots and
short-lived download authorization. Production signing remains external.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable


class PrivateDistributionError(ValueError):
    pass


def _text(v: str, field: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise PrivateDistributionError(f"{field} must be non-empty text")
    return v.strip()


def _hex64(v: str, field: str) -> str:
    v = _text(v, field).lower()
    if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise PrivateDistributionError(f"{field} must be a 32-byte hex digest")
    return v


def _epoch(v: int, field: str) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise PrivateDistributionError(f"{field} must be a non-negative integer")
    return v


@dataclass(frozen=True, slots=True)
class ChannelArtifact:
    product: str
    version: str
    channel: str
    artifact_sha256: str
    policy_hash: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ChannelManifest:
    sequence: int
    issued_epoch: int
    expires_after_epoch: int
    artifacts: tuple[ChannelArtifact, ...]


@dataclass(frozen=True, slots=True)
class RevocationSnapshot:
    sequence: int
    issued_epoch: int
    revoked_artifact_sha256: tuple[str, ...]
    revoked_entitlement_digests: tuple[str, ...]
    revoked_lease_ids: tuple[str, ...]
    revoked_seat_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DownloadGrant:
    grant_id: str
    customer_id: str
    entitlement_digest: str
    artifact_sha256: str
    channel: str
    not_before_epoch: int
    expires_after_epoch: int


def canonical_manifest_payload(manifest: ChannelManifest) -> bytes:
    if not isinstance(manifest, ChannelManifest):
        raise PrivateDistributionError("manifest must be ChannelManifest")
    seq = _epoch(manifest.sequence, "sequence")
    issued = _epoch(manifest.issued_epoch, "issued_epoch")
    expiry = _epoch(manifest.expires_after_epoch, "expires_after_epoch")
    if expiry < issued:
        raise PrivateDistributionError("manifest expiry cannot precede issue")
    rows = []
    seen = set()
    for a in manifest.artifacts:
        if not isinstance(a, ChannelArtifact):
            raise PrivateDistributionError("artifact row invalid")
        sha = _hex64(a.artifact_sha256, "artifact_sha256")
        if sha in seen:
            raise PrivateDistributionError("duplicate artifact digest")
        seen.add(sha)
        if not isinstance(a.size_bytes, int) or isinstance(a.size_bytes, bool) or a.size_bytes < 1:
            raise PrivateDistributionError("size_bytes must be >= 1")
        rows.append({
            "product": _text(a.product, "product"),
            "version": _text(a.version, "version"),
            "channel": _text(a.channel, "channel"),
            "artifact_sha256": sha,
            "policy_hash": _hex64(a.policy_hash, "policy_hash"),
            "size_bytes": a.size_bytes,
        })
    obj = {"schema":"koschei/private-channel-manifest/v1","sequence":seq,
           "issued_epoch":issued,"expires_after_epoch":expiry,
           "artifacts":sorted(rows, key=lambda x:(x["product"],x["version"],x["artifact_sha256"]))}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_revocation_payload(snapshot: RevocationSnapshot) -> bytes:
    if not isinstance(snapshot, RevocationSnapshot):
        raise PrivateDistributionError("snapshot must be RevocationSnapshot")
    obj = {
        "schema":"koschei/revocation-snapshot/v1",
        "sequence":_epoch(snapshot.sequence,"sequence"),
        "issued_epoch":_epoch(snapshot.issued_epoch,"issued_epoch"),
        "revoked_artifact_sha256":sorted({_hex64(x,"revoked_artifact_sha256") for x in snapshot.revoked_artifact_sha256}),
        "revoked_entitlement_digests":sorted({_hex64(x,"revoked_entitlement_digest") for x in snapshot.revoked_entitlement_digests}),
        "revoked_lease_ids":sorted({_text(x,"revoked_lease_id") for x in snapshot.revoked_lease_ids}),
        "revoked_seat_ids":sorted({_text(x,"revoked_seat_id") for x in snapshot.revoked_seat_ids}),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_download_grant_payload(grant: DownloadGrant) -> bytes:
    if not isinstance(grant, DownloadGrant):
        raise PrivateDistributionError("grant must be DownloadGrant")
    start = _epoch(grant.not_before_epoch,"not_before_epoch")
    end = _epoch(grant.expires_after_epoch,"expires_after_epoch")
    if end < start:
        raise PrivateDistributionError("download grant expiry cannot precede start")
    obj = {"schema":"koschei/download-grant/v1","grant_id":_text(grant.grant_id,"grant_id"),
           "customer_id":_text(grant.customer_id,"customer_id"),
           "entitlement_digest":_hex64(grant.entitlement_digest,"entitlement_digest"),
           "artifact_sha256":_hex64(grant.artifact_sha256,"artifact_sha256"),
           "channel":_text(grant.channel,"channel"),"not_before_epoch":start,
           "expires_after_epoch":end}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def verify_private_download(*, manifest: ChannelManifest, manifest_signature: bytes,
                            manifest_verifier: Callable[[bytes, bytes], bool],
                            revocations: RevocationSnapshot, revocation_signature: bytes,
                            revocation_verifier: Callable[[bytes, bytes], bool],
                            grant: DownloadGrant, grant_signature: bytes,
                            grant_verifier: Callable[[bytes, bytes], bool],
                            current_epoch: int, expected_channel: str,
                            expected_policy_hash: str, expected_size_bytes: int,
                            artifact_bytes: bytes) -> bool:
    """Fail-closed final gate before updater accepts an artifact."""
    try:
        now = _epoch(current_epoch,"current_epoch")
        if not manifest_verifier(canonical_manifest_payload(manifest), manifest_signature):
            return False
        if not revocation_verifier(canonical_revocation_payload(revocations), revocation_signature):
            return False
        if not grant_verifier(canonical_download_grant_payload(grant), grant_signature):
            return False
        if now < manifest.issued_epoch or now > manifest.expires_after_epoch:
            return False
        if now < grant.not_before_epoch or now > grant.expires_after_epoch:
            return False
        channel = _text(expected_channel,"expected_channel")
        if grant.channel != channel:
            return False
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        if digest != grant.artifact_sha256:
            return False
        if digest in set(revocations.revoked_artifact_sha256):
            return False
        row = next((a for a in manifest.artifacts if a.artifact_sha256 == digest), None)
        if row is None or row.channel != channel:
            return False
        if row.policy_hash != _hex64(expected_policy_hash,"expected_policy_hash"):
            return False
        if row.size_bytes != expected_size_bytes or len(artifact_bytes) != row.size_bytes:
            return False
        return True
    except (PrivateDistributionError, TypeError, ValueError):
        return False
