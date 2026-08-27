"""Provider-neutral remote attestation evidence for Koschei Lang v1.

This module binds opaque raw attestation evidence to canonical environment/workload
measurements, a trust-root identity and freshness epoch through a trusted verifier
receipt. It does not implement TPM/TEE/cloud parsing itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

_CTX = b"koschei.remote-attestation-evidence/v1\x00"
_RAW_CTX = b"koschei.remote-attestation-raw/v1\x00"


class RemoteAttestationEvidenceV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise RemoteAttestationEvidenceV1Error("remote_attestation_verifier_key must contain at least 32 bytes")
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RemoteAttestationEvidenceV1Error(f"{label} cannot be empty")
    return value.strip()


def _epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RemoteAttestationEvidenceV1Error("epoch must be a non-negative integer")
    return value


def measure_raw_remote_attestation_v1(raw_evidence_bytes: bytes) -> str:
    if not isinstance(raw_evidence_bytes, bytes) or not raw_evidence_bytes:
        raise RemoteAttestationEvidenceV1Error("raw_evidence_bytes must be non-empty bytes")
    return hashlib.sha256(_RAW_CTX + raw_evidence_bytes).hexdigest()


def _payload(*, provider_id: str, trust_root_id: str, raw_evidence_digest: str,
             environment_digest: str, workload_digest: str, observed_epoch: int,
             expires_before_epoch: int) -> bytes:
    rows = (
        f"provider={provider_id}", f"trust_root={trust_root_id}",
        f"raw={raw_evidence_digest}", f"environment={environment_digest}",
        f"workload={workload_digest}", f"observed_epoch={observed_epoch}",
        f"expires_before_epoch={expires_before_epoch}", "verified=1", "authority=0",
    )
    return _CTX + "\n".join(rows).encode()


@dataclass(frozen=True, slots=True)
class RemoteAttestationEvidenceV1:
    provider_id: str
    trust_root_id: str
    raw_evidence_digest: str
    environment_digest: str
    workload_digest: str
    observed_epoch: int
    expires_before_epoch: int
    evidence_digest: str
    verified: bool = True
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, remote_attestation_verifier_key: bytes,
                             raw_evidence_bytes: bytes, current_epoch: int) -> None:
        key = _key(remote_attestation_verifier_key)
        current = _epoch(current_epoch)
        if self.authority or self.verified is not True:
            raise RemoteAttestationEvidenceV1Error("remote attestation evidence must remain verified and non-authoritative")
        if self.raw_evidence_digest != measure_raw_remote_attestation_v1(raw_evidence_bytes):
            raise RemoteAttestationEvidenceV1Error("remote attestation raw evidence mismatch")
        observed = _epoch(self.observed_epoch)
        expires = _epoch(self.expires_before_epoch)
        if expires <= observed:
            raise RemoteAttestationEvidenceV1Error("remote attestation expiry must be after observed epoch")
        if current < observed:
            raise RemoteAttestationEvidenceV1Error("remote attestation evidence is from the future")
        if current >= expires:
            raise RemoteAttestationEvidenceV1Error("remote attestation evidence is stale")
        expected = hmac.new(key, _payload(
            provider_id=_text(self.provider_id, "provider_id"),
            trust_root_id=_text(self.trust_root_id, "trust_root_id"),
            raw_evidence_digest=self.raw_evidence_digest,
            environment_digest=_text(self.environment_digest, "environment_digest"),
            workload_digest=_text(self.workload_digest, "workload_digest"),
            observed_epoch=observed, expires_before_epoch=expires,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.evidence_digest, expected):
            raise RemoteAttestationEvidenceV1Error("remote attestation evidence authentication failed")


def attest_remote_environment_evidence_v1(*, provider_id: str, trust_root_id: str,
                                          raw_evidence_bytes: bytes,
                                          environment_digest: str,
                                          workload_digest: str,
                                          observed_epoch: int,
                                          expires_before_epoch: int,
                                          remote_attestation_verifier_key: bytes) -> RemoteAttestationEvidenceV1:
    key = _key(remote_attestation_verifier_key)
    observed = _epoch(observed_epoch); expires = _epoch(expires_before_epoch)
    if expires <= observed:
        raise RemoteAttestationEvidenceV1Error("remote attestation expiry must be after observed epoch")
    result = RemoteAttestationEvidenceV1(
        provider_id=_text(provider_id, "provider_id"),
        trust_root_id=_text(trust_root_id, "trust_root_id"),
        raw_evidence_digest=measure_raw_remote_attestation_v1(raw_evidence_bytes),
        environment_digest=_text(environment_digest, "environment_digest"),
        workload_digest=_text(workload_digest, "workload_digest"),
        observed_epoch=observed, expires_before_epoch=expires, evidence_digest="",
    )
    object.__setattr__(result, "evidence_digest", hmac.new(key, _payload(
        provider_id=result.provider_id, trust_root_id=result.trust_root_id,
        raw_evidence_digest=result.raw_evidence_digest,
        environment_digest=result.environment_digest, workload_digest=result.workload_digest,
        observed_epoch=result.observed_epoch, expires_before_epoch=result.expires_before_epoch,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(remote_attestation_verifier_key=key, raw_evidence_bytes=raw_evidence_bytes, current_epoch=observed)
    return result
