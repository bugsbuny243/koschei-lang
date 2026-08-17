"""Protected source envelope and trusted materialization gate v1.

This module keeps durable protected-artifact validity separate from short-lived
build authority.  A manifest, path, or caller-supplied boolean is never treated
as authority.  Canonical source is materialized only when the durable envelope,
local Trust Plane policy, explicit build capability, scoped build grant, sealed
artifact and canonical plaintext hash all agree.

The encrypted/sealed artifact bytes remain external to the metadata envelope so
storage backends can rotate or relocate opaque objects without creating a normal
plaintext project file.  Decryption is delegated to a Trust Plane callback; this
module never derives canonical keys from human-readable time codes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import hmac
from typing import Callable, Iterable

from .decoy_view_broker_v1 import SourceView, read_source_view


SCHEMA_VERSION = 1
BUILD_SCOPE = "protected-source:build"
MATERIALIZE_CAPABILITY = "protected-source:materialize"


class ProtectedSourceEnvelopeError(ValueError):
    """Raised when protected-source admission fails closed."""


@dataclass(frozen=True, slots=True)
class ProtectedSourceEnvelope:
    version: int
    project_id: str
    object_id: str
    canonical_artifact_hash: str
    protected_artifact_hash: str
    cipher_suite_id: str
    wrapped_data_key_ref: str
    policy_hash: str
    integrity_algorithm: str
    integrity_tag: str


@dataclass(frozen=True, slots=True)
class BuildAuthorization:
    project_id: str
    object_id: str
    policy_hash: str
    scope: str
    not_before_epoch: int
    expires_after_epoch: int
    nonce: str
    mac: str


@dataclass(frozen=True, slots=True)
class TrustPlanePolicy:
    project_id: str
    policy_hash: str
    capabilities: tuple[str, ...]
    protected_source_required: bool = True


@dataclass(frozen=True, slots=True)
class MaterializationAuditEvent:
    project_id: str
    object_id: str
    epoch: int
    outcome: str
    reason: str


Decryptor = Callable[[str, str, bytes], bytearray]
AuditSink = Callable[[MaterializationAuditEvent], None]


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtectedSourceEnvelopeError(f"{field} must be non-empty text")
    if "\x00" in value:
        raise ProtectedSourceEnvelopeError(f"{field} cannot contain NUL")
    return value


def _require_object_id(value: str) -> str:
    oid = _require_text(value, "object_id").lower()
    if len(oid) < 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise ProtectedSourceEnvelopeError("object_id must be >=128-bit hexadecimal")
    return oid


def _require_hash(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ProtectedSourceEnvelopeError(f"{field} must be sha256 text")
    digest = value[7:]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ProtectedSourceEnvelopeError(f"{field} is malformed")
    return value


def _require_epoch(value: int, field: str = "epoch") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProtectedSourceEnvelopeError(f"{field} must be a non-negative integer")
    return value


def _require_key(value: bytes, field: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ProtectedSourceEnvelopeError(f"{field} must contain at least 256 bits")
    return value


def _require_nonce(value: str) -> str:
    nonce = _require_text(value, "nonce")
    if len(nonce) < 16:
        raise ProtectedSourceEnvelopeError("nonce must contain at least 16 characters")
    return nonce


def _require_mac(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ProtectedSourceEnvelopeError(f"{field} must be a SHA-256 HMAC hex digest")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ProtectedSourceEnvelopeError(f"{field} must be lowercase hexadecimal")
    return value


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _sha256(data: bytes | bytearray) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _envelope_message(envelope: ProtectedSourceEnvelope) -> bytes:
    if not isinstance(envelope, ProtectedSourceEnvelope):
        raise ProtectedSourceEnvelopeError("invalid protected source envelope")
    if envelope.version != SCHEMA_VERSION:
        raise ProtectedSourceEnvelopeError("unsupported protected source envelope version")
    project = _require_text(envelope.project_id, "project_id")
    oid = _require_object_id(envelope.object_id)
    canonical_hash = _require_hash(envelope.canonical_artifact_hash, "canonical_artifact_hash")
    protected_hash = _require_hash(envelope.protected_artifact_hash, "protected_artifact_hash")
    cipher = _require_text(envelope.cipher_suite_id, "cipher_suite_id")
    wrapped_ref = _require_text(envelope.wrapped_data_key_ref, "wrapped_data_key_ref")
    policy_hash = _require_hash(envelope.policy_hash, "policy_hash")
    if envelope.integrity_algorithm != "hmac-sha256":
        raise ProtectedSourceEnvelopeError("unsupported protected source envelope integrity algorithm")
    return (
        b"koschei/protected-source-envelope/v1\x00"
        + _frame(str(envelope.version).encode("ascii"))
        + _frame(project.encode("utf-8"))
        + _frame(oid.encode("ascii"))
        + _frame(canonical_hash.encode("ascii"))
        + _frame(protected_hash.encode("ascii"))
        + _frame(cipher.encode("utf-8"))
        + _frame(wrapped_ref.encode("utf-8"))
        + _frame(policy_hash.encode("ascii"))
        + _frame(envelope.integrity_algorithm.encode("ascii"))
    )


def create_protected_source_envelope(
    *,
    project_id: str,
    object_id: str,
    canonical_source: bytes,
    protected_artifact: bytes,
    cipher_suite_id: str,
    wrapped_data_key_ref: str,
    policy_hash: str,
    integrity_key: bytes,
) -> ProtectedSourceEnvelope:
    """Create authenticated metadata for an already encrypted/sealed artifact."""
    if not isinstance(canonical_source, bytes):
        raise ProtectedSourceEnvelopeError("canonical_source must be bytes")
    if not isinstance(protected_artifact, bytes):
        raise ProtectedSourceEnvelopeError("protected_artifact must be bytes")
    key = _require_key(integrity_key, "integrity_key")
    envelope = ProtectedSourceEnvelope(
        version=SCHEMA_VERSION,
        project_id=_require_text(project_id, "project_id"),
        object_id=_require_object_id(object_id),
        canonical_artifact_hash=_sha256(canonical_source),
        protected_artifact_hash=_sha256(protected_artifact),
        cipher_suite_id=_require_text(cipher_suite_id, "cipher_suite_id"),
        wrapped_data_key_ref=_require_text(wrapped_data_key_ref, "wrapped_data_key_ref"),
        policy_hash=_require_hash(policy_hash, "policy_hash"),
        integrity_algorithm="hmac-sha256",
        integrity_tag="",
    )
    tag = hmac.new(key, _envelope_message(envelope), hashlib.sha256).hexdigest()
    return replace(envelope, integrity_tag=tag)


def verify_envelope_integrity(
    envelope: ProtectedSourceEnvelope,
    *,
    protected_artifact: bytes,
    integrity_key: bytes,
) -> None:
    """Verify durable envelope/artifact integrity independently of build auth."""
    if not isinstance(protected_artifact, bytes):
        raise ProtectedSourceEnvelopeError("protected_artifact must be bytes")
    key = _require_key(integrity_key, "integrity_key")
    message = _envelope_message(envelope)
    claimed_tag = _require_mac(envelope.integrity_tag, "integrity_tag")
    if not hmac.compare_digest(_sha256(protected_artifact), envelope.protected_artifact_hash):
        raise ProtectedSourceEnvelopeError("protected artifact hash mismatch")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, claimed_tag):
        raise ProtectedSourceEnvelopeError("protected source envelope integrity mismatch")


def _build_authorization_message(grant: BuildAuthorization) -> bytes:
    if not isinstance(grant, BuildAuthorization):
        raise ProtectedSourceEnvelopeError("invalid build authorization")
    project = _require_text(grant.project_id, "grant.project_id")
    oid = _require_object_id(grant.object_id)
    policy_hash = _require_hash(grant.policy_hash, "grant.policy_hash")
    scope = _require_text(grant.scope, "grant.scope")
    start = _require_epoch(grant.not_before_epoch, "grant.not_before_epoch")
    end = _require_epoch(grant.expires_after_epoch, "grant.expires_after_epoch")
    if end < start:
        raise ProtectedSourceEnvelopeError("build authorization expiry cannot precede start")
    nonce = _require_nonce(grant.nonce)
    return (
        b"koschei/protected-source-build-authorization/v1\x00"
        + _frame(project.encode("utf-8"))
        + _frame(oid.encode("ascii"))
        + _frame(policy_hash.encode("ascii"))
        + _frame(scope.encode("ascii"))
        + _frame(str(start).encode("ascii"))
        + _frame(str(end).encode("ascii"))
        + _frame(nonce.encode("utf-8"))
    )


def issue_build_authorization(
    *,
    project_id: str,
    object_id: str,
    policy_hash: str,
    not_before_epoch: int,
    expires_after_epoch: int,
    nonce: str,
    authorization_key: bytes,
    scope: str = BUILD_SCOPE,
) -> BuildAuthorization:
    key = _require_key(authorization_key, "authorization_key")
    grant = BuildAuthorization(
        project_id=_require_text(project_id, "project_id"),
        object_id=_require_object_id(object_id),
        policy_hash=_require_hash(policy_hash, "policy_hash"),
        scope=_require_text(scope, "scope"),
        not_before_epoch=_require_epoch(not_before_epoch, "not_before_epoch"),
        expires_after_epoch=_require_epoch(expires_after_epoch, "expires_after_epoch"),
        nonce=_require_nonce(nonce),
        mac="",
    )
    message = _build_authorization_message(grant)
    mac = hmac.new(key, message, hashlib.sha256).hexdigest()
    return replace(grant, mac=mac)


def verify_build_authorization(
    grant: BuildAuthorization,
    *,
    project_id: str,
    object_id: str,
    policy_hash: str,
    epoch: int,
    authorization_key: bytes,
) -> None:
    key = _require_key(authorization_key, "authorization_key")
    ep = _require_epoch(epoch)
    message = _build_authorization_message(grant)
    claimed_mac = _require_mac(grant.mac, "grant.mac")
    if grant.scope != BUILD_SCOPE:
        raise ProtectedSourceEnvelopeError("build authorization has wrong scope")
    if grant.project_id != _require_text(project_id, "project_id"):
        raise ProtectedSourceEnvelopeError("build authorization project mismatch")
    if grant.object_id != _require_object_id(object_id):
        raise ProtectedSourceEnvelopeError("build authorization object mismatch")
    if grant.policy_hash != _require_hash(policy_hash, "policy_hash"):
        raise ProtectedSourceEnvelopeError("build authorization policy mismatch")
    if ep < grant.not_before_epoch or ep > grant.expires_after_epoch:
        raise ProtectedSourceEnvelopeError("build authorization is not valid for current epoch")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, claimed_mac):
        raise ProtectedSourceEnvelopeError("build authorization MAC is invalid")


def _normalize_capabilities(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProtectedSourceEnvelopeError("capabilities must be an iterable of capability names")
    result: list[str] = []
    for value in values:
        result.append(_require_text(value, "capability"))
    return tuple(result)


def _validate_local_policy(envelope: ProtectedSourceEnvelope, policy: TrustPlanePolicy) -> None:
    if not isinstance(policy, TrustPlanePolicy):
        raise ProtectedSourceEnvelopeError("local Trust Plane policy is required")
    if policy.protected_source_required is not True:
        raise ProtectedSourceEnvelopeError("protected project cannot downgrade to plaintext lane")
    if policy.project_id != envelope.project_id:
        raise ProtectedSourceEnvelopeError("local Trust Plane project mismatch")
    if _require_hash(policy.policy_hash, "local policy_hash") != envelope.policy_hash:
        raise ProtectedSourceEnvelopeError("protected source policy hash mismatch")
    capabilities = _normalize_capabilities(policy.capabilities)
    if MATERIALIZE_CAPABILITY not in capabilities:
        raise ProtectedSourceEnvelopeError("explicit protected-source materialization capability is missing")


def _audit(
    sink: AuditSink | None,
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    outcome: str,
    reason: str,
) -> None:
    if sink is None:
        return
    if not callable(sink):
        raise ProtectedSourceEnvelopeError("audit_sink must be callable")
    sink(MaterializationAuditEvent(project_id, object_id, epoch, outcome, reason))


def materialize_canonical_source(
    envelope: ProtectedSourceEnvelope,
    *,
    protected_artifact: bytes,
    policy: TrustPlanePolicy,
    build_authorization: BuildAuthorization,
    epoch: int,
    integrity_key: bytes,
    authorization_key: bytes,
    canonical_view_key: bytes,
    decryptor: Decryptor,
    audit_sink: AuditSink | None = None,
) -> SourceView:
    """Materialize one canonical build view through the Trust Plane gate.

    ``decryptor`` must return a mutable ``bytearray`` so this layer can wipe its
    temporary plaintext buffer in ``finally``.  The returned immutable SourceView
    is the intentionally admitted build-lifetime copy and must remain scoped to
    that build session.  No plaintext file is created here.
    """
    ep = _require_epoch(epoch)
    project = envelope.project_id if isinstance(envelope, ProtectedSourceEnvelope) else "<invalid>"
    oid = envelope.object_id if isinstance(envelope, ProtectedSourceEnvelope) else "<invalid>"
    try:
        verify_envelope_integrity(
            envelope,
            protected_artifact=protected_artifact,
            integrity_key=integrity_key,
        )
        _validate_local_policy(envelope, policy)
        verify_build_authorization(
            build_authorization,
            project_id=envelope.project_id,
            object_id=envelope.object_id,
            policy_hash=envelope.policy_hash,
            epoch=ep,
            authorization_key=authorization_key,
        )
        _require_key(canonical_view_key, "canonical_view_key")
        if not callable(decryptor):
            raise ProtectedSourceEnvelopeError("Trust Plane decryptor must be callable")

        plaintext = decryptor(
            envelope.cipher_suite_id,
            envelope.wrapped_data_key_ref,
            protected_artifact,
        )
        if not isinstance(plaintext, bytearray):
            raise ProtectedSourceEnvelopeError("Trust Plane decryptor must return mutable bytearray plaintext")
        try:
            if not hmac.compare_digest(_sha256(plaintext), envelope.canonical_artifact_hash):
                raise ProtectedSourceEnvelopeError("canonical artifact hash mismatch after materialization")
            canonical = bytes(plaintext)
            view = read_source_view(
                project_id=envelope.project_id,
                object_id=envelope.object_id,
                epoch=ep,
                authorized=True,
                canonical_reader=lambda expected_oid: canonical
                if expected_oid == envelope.object_id
                else (_raise_object_mismatch()),
                deception_key=b"\x00" * 32,
                canonical_view_key=canonical_view_key,
            )
        finally:
            for index in range(len(plaintext)):
                plaintext[index] = 0
        _audit(
            audit_sink,
            project_id=envelope.project_id,
            object_id=envelope.object_id,
            epoch=ep,
            outcome="admitted",
            reason="canonical-materialization-admitted",
        )
        return view
    except ProtectedSourceEnvelopeError as error:
        _audit(
            audit_sink,
            project_id=project,
            object_id=oid,
            epoch=ep,
            outcome="denied",
            reason=str(error),
        )
        raise


def _raise_object_mismatch() -> bytes:
    raise ProtectedSourceEnvelopeError("canonical reader object mismatch")
