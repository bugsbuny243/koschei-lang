"""Koschei-native Admission Reality v1.

Admission is the membrane between an immutable Intent Reality and a world adapter.
It does not execute the intent. It proves that an independently issued authority
matches the exact intent, adapter, action, project, epoch and bounded time window.

This keeps desire, permission and effect as three different realities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .native_intent_reality_v1 import IntentRealityV1, verify_native_intent_reality_v1

_CONTEXT = b"koschei.native-admission-reality/v1\x00"


class NativeAdmissionRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdmissionAuthorityV1:
    project_commitment: bytes
    epoch: int
    intent_digest: bytes
    adapter: str
    action: str
    not_before: int
    expires_at: int
    authority_digest: bytes

    def __repr__(self) -> str:
        return (
            f"AdmissionAuthorityV1(project=<committed>, epoch={self.epoch}, "
            f"adapter={self.adapter!r}, action={self.action!r}, window=<bounded>, "
            "authority=<committed>)"
        )


@dataclass(frozen=True, slots=True)
class AdmittedIntentV1:
    project_commitment: bytes
    epoch: int
    intent_digest: bytes
    authority_digest: bytes
    admission_digest: bytes


def _fail(message: str) -> None:
    raise NativeAdmissionRealityError(message)


def _d32(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        _fail(f"{label} must be exactly 32 bytes")
    return value


def issue_admission_authority_v1(*, project_commitment: bytes, epoch: int,
    intent: IntentRealityV1, not_before: int, expires_at: int,
    host_nonce: bytes) -> AdmissionAuthorityV1:
    project = _d32(project_commitment, "project commitment")
    nonce = _d32(host_nonce, "host nonce")
    try:
        verify_native_intent_reality_v1(intent)
    except Exception as error:
        raise NativeAdmissionRealityError("canonical intent required") from error
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _fail("epoch must be positive")
    if not isinstance(not_before, int) or not isinstance(expires_at, int) or expires_at <= not_before:
        _fail("invalid admission window")
    if expires_at - not_before > 900:
        _fail("admission authority window exceeds fifteen minutes")
    payload = b"\x00".join((project, epoch.to_bytes(8, "big"), intent.intent_digest,
        intent.adapter.encode("utf-8"), intent.action.encode("utf-8"),
        not_before.to_bytes(8, "big"), expires_at.to_bytes(8, "big"), nonce))
    digest = hashlib.sha3_256(_CONTEXT + b"authority\x00" + payload).digest()
    return AdmissionAuthorityV1(project, epoch, intent.intent_digest, intent.adapter,
        intent.action, not_before, expires_at, digest)


def admit_native_intent_reality_v1(intent: IntentRealityV1,
    authority: AdmissionAuthorityV1, *, now: int) -> AdmittedIntentV1:
    try:
        verify_native_intent_reality_v1(intent)
    except Exception as error:
        raise NativeAdmissionRealityError("canonical intent required") from error
    if not isinstance(authority, AdmissionAuthorityV1):
        _fail("canonical AdmissionAuthorityV1 required")
    if not isinstance(now, int) or now < authority.not_before or now >= authority.expires_at:
        _fail("admission authority is not active")
    if authority.intent_digest != intent.intent_digest:
        _fail("authority does not match exact intent")
    if authority.adapter != intent.adapter or authority.action != intent.action:
        _fail("authority target/action mismatch")
    payload = b"\x00".join((authority.project_commitment,
        authority.epoch.to_bytes(8, "big"), intent.intent_digest, authority.authority_digest))
    digest = hashlib.sha3_256(_CONTEXT + b"admitted\x00" + payload).digest()
    return AdmittedIntentV1(authority.project_commitment, authority.epoch,
        intent.intent_digest, authority.authority_digest, digest)
