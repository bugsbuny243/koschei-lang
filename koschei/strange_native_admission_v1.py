"""Independent, authority-free admission of exact native build bytes for Strange.

This is a trusted-boundary *evidence* contract, not an execution permit. Native
bytes, customer Veyra, deployment, canonical MIR, Continuity epoch, and the
120-second issue window are bound by an externally held attestation key.
A compromised Python verifier or caller-supplied key is NOT a hardware root.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .strange_representation_epoch_v1 import (
    StrangeEpochProjectionV1,
    StrangeRepresentationEpochError,
    _fingerprint,
    _frame,
    _text,
    require_strange_epoch_window_v1,
)

_CTX = b"koschei/strange-native-admission/v1\x00"


class StrangeNativeAdmissionError(ValueError):
    """Build evidence is missing, stale, mismatched, or unauthenticated."""


@dataclass(frozen=True, slots=True)
class StrangeNativeAttestationV1:
    """Trust-Plane statement of native binary identity; no effect authority."""

    source_sha256: str
    native_sha256: str
    scope_binding: str
    attestation_mac: str
    epoch: int
    starts_at_seconds: int
    expires_before_seconds: int
    authority: bool = False
    version: int = 1


def _attestation_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise StrangeNativeAdmissionError("independent attestation key must contain at least 256 bits")
    return value


def _digest(value: str, label: str) -> bytes:
    try:
        return _fingerprint(value, label)
    except StrangeRepresentationEpochError as exc:
        raise StrangeNativeAdmissionError(f"invalid {label}") from exc


def _scope(
    *,
    key: bytes,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    continuity: ContinuityEpochAuthorityV1,
    epoch: int,
    starts_at_seconds: int,
) -> str:
    try:
        continuity.assert_sealed()
        fields = (
            _text(deployment_id, "deployment ID"),
            _fingerprint(veyra_digest, "Veyra digest"),
            _fingerprint(mir_fingerprint, "MIR fingerprint"),
            _fingerprint(continuity.authority_digest, "Continuity digest"),
            epoch.to_bytes(8, "big"),
            starts_at_seconds.to_bytes(8, "big"),
        )
    except (ValueError, OverflowError, AttributeError) as exc:
        raise StrangeNativeAdmissionError("invalid attestation scope") from exc
    return hmac.new(key, _CTX + b"scope\x00" + b"".join(_frame(x) for x in fields), hashlib.sha256).hexdigest()


def _mac(key: bytes, evidence: StrangeNativeAttestationV1) -> str:
    material = b"".join(
        _frame(field) for field in (
            _digest(evidence.source_sha256, "source SHA256"),
            _digest(evidence.native_sha256, "native SHA256"),
            _digest(evidence.scope_binding, "scope binding"),
            evidence.epoch.to_bytes(8, "big"),
            evidence.starts_at_seconds.to_bytes(8, "big"),
            evidence.expires_before_seconds.to_bytes(8, "big"),
            b"authority=0;version=1",
        )
    )
    return hmac.new(key, _CTX + b"attestation\x00" + material, hashlib.sha256).hexdigest()


def _check_receipt(
    receipt: StrangeEpochProjectionV1,
    *,
    epoch: int,
    starts_at_seconds: int,
) -> None:
    if not isinstance(receipt, StrangeEpochProjectionV1):
        raise StrangeNativeAdmissionError("exact Strange build receipt required")
    if receipt.version != 1 or receipt.authority is not False:
        raise StrangeNativeAdmissionError("non-authoritative v1 build receipt required")
    if (
        receipt.epoch != epoch
        or receipt.starts_at_seconds != starts_at_seconds
        or receipt.expires_before_seconds != starts_at_seconds + 120
    ):
        raise StrangeNativeAdmissionError("build receipt epoch/window mismatch")
    _digest(receipt.source_sha256, "source SHA256")


def _current(
    continuity: ContinuityEpochAuthorityV1,
    epoch: int,
    start: int,
    seconds_reader: Callable[[], int],
) -> None:
    try:
        require_strange_epoch_window_v1(
            continuity=continuity,
            expected_epoch=epoch,
            starts_at_seconds=start,
            seconds_reader=seconds_reader,
        )
    except StrangeRepresentationEpochError as exc:
        raise StrangeNativeAdmissionError("Continuity/time admission failed closed") from exc


def issue_strange_native_attestation_v1(
    *,
    receipt: StrangeEpochProjectionV1,
    native_binary: bytes,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
    attestation_key: bytes,
) -> StrangeNativeAttestationV1:
    """Trusted issuer attests exact native bytes after a separate verified build.

    The issuer MUST independently verify the source->binary compiler/provenance
    link before calling this function. This function does not compile Go.
    """
    key = _attestation_key(attestation_key)
    _check_receipt(receipt, epoch=expected_epoch, starts_at_seconds=starts_at_seconds)
    _current(continuity, expected_epoch, starts_at_seconds, seconds_reader)
    if not isinstance(native_binary, bytes) or not native_binary:
        raise StrangeNativeAdmissionError("nonempty native binary bytes required")
    scope = _scope(
        key=key, deployment_id=deployment_id, veyra_digest=veyra_digest,
        mir_fingerprint=mir_fingerprint, continuity=continuity,
        epoch=expected_epoch, starts_at_seconds=starts_at_seconds,
    )
    evidence = StrangeNativeAttestationV1(
        source_sha256=receipt.source_sha256,
        native_sha256=hashlib.sha256(native_binary).hexdigest(),
        scope_binding=scope,
        attestation_mac="",
        epoch=expected_epoch,
        starts_at_seconds=starts_at_seconds,
        expires_before_seconds=receipt.expires_before_seconds,
    )
    signed = StrangeNativeAttestationV1(
        source_sha256=evidence.source_sha256,
        native_sha256=evidence.native_sha256,
        scope_binding=evidence.scope_binding,
        attestation_mac=_mac(key, evidence),
        epoch=evidence.epoch,
        starts_at_seconds=evidence.starts_at_seconds,
        expires_before_seconds=evidence.expires_before_seconds,
    )
    _current(continuity, expected_epoch, starts_at_seconds, seconds_reader)
    return signed


def verify_strange_native_admission_v1(
    *,
    attestation: StrangeNativeAttestationV1,
    native_binary: bytes,
    expected_source_sha256: str,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
    attestation_key: bytes,
) -> None:
    """Fail closed on wrong binary, customer, epoch, proof, or current time.

    Successful verification is NOT permission to execute a privileged effect.
    """
    key = _attestation_key(attestation_key)
    _current(continuity, expected_epoch, starts_at_seconds, seconds_reader)
    if not isinstance(attestation, StrangeNativeAttestationV1):
        raise StrangeNativeAdmissionError("native attestation v1 required")
    if attestation.version != 1 or attestation.authority is not False:
        raise StrangeNativeAdmissionError("attestation cannot grant authority")
    if (
        attestation.epoch != expected_epoch
        or attestation.starts_at_seconds != starts_at_seconds
        or attestation.expires_before_seconds != starts_at_seconds + 120
    ):
        raise StrangeNativeAdmissionError("native attestation epoch/window mismatch")
    if not isinstance(native_binary, bytes) or not native_binary:
        raise StrangeNativeAdmissionError("native binary bytes required")
    _digest(expected_source_sha256, "expected source SHA256")
    # Dataclasses can be constructed by untrusted callers. Validate both type
    # and canonical digest format before constant-time comparisons.
    _digest(attestation.source_sha256, "attested source SHA256")
    _digest(attestation.native_sha256, "attested native SHA256")
    _digest(attestation.scope_binding, "attested scope binding")
    _digest(attestation.attestation_mac, "attestation MAC")
    if not hmac.compare_digest(attestation.source_sha256, expected_source_sha256):
        raise StrangeNativeAdmissionError("source provenance mismatch")
    binary_digest = hashlib.sha256(native_binary).hexdigest()
    if not hmac.compare_digest(binary_digest, attestation.native_sha256):
        raise StrangeNativeAdmissionError("native binary digest mismatch")
    expected_scope = _scope(
        key=key, deployment_id=deployment_id, veyra_digest=veyra_digest,
        mir_fingerprint=mir_fingerprint, continuity=continuity,
        epoch=expected_epoch, starts_at_seconds=starts_at_seconds,
    )
    if not hmac.compare_digest(attestation.scope_binding, expected_scope):
        raise StrangeNativeAdmissionError("native attestation scope mismatch")
    try:
        expected_mac = _mac(key, attestation)
    except (ValueError, OverflowError) as exc:
        raise StrangeNativeAdmissionError("malformed native attestation") from exc
    if not hmac.compare_digest(expected_mac, attestation.attestation_mac):
        raise StrangeNativeAdmissionError("native attestation authentication failed")
    _current(continuity, expected_epoch, starts_at_seconds, seconds_reader)
