"""Short-lived read authorization for Koschei protected source views.

The authorization decision is cryptographic and epoch-bound. Callers never pass
a naked boolean into the protected read broker in this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .decoy_view_broker_v1 import SourceView, read_source_view


class ReadAuthorizationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReadGrant:
    project_id: str
    object_id: str
    not_before_epoch: int
    expires_after_epoch: int
    nonce: str
    mac: str


def _valid_project_id(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReadAuthorizationError("project_id must be non-empty text")
    if "\x00" in value:
        raise ReadAuthorizationError("project_id cannot contain NUL")
    return value


def _valid_oid(value: str) -> str:
    if not isinstance(value, str):
        raise ReadAuthorizationError("object_id must be text")
    oid = value.lower()
    if len(oid) < 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise ReadAuthorizationError("object_id must be >=128-bit hexadecimal")
    return oid


def _valid_epoch(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReadAuthorizationError(f"{field} must be a non-negative integer")
    return value


def _valid_nonce(value: str) -> str:
    if not isinstance(value, str) or len(value) < 16:
        raise ReadAuthorizationError("nonce must contain at least 16 characters")
    if "\x00" in value:
        raise ReadAuthorizationError("nonce cannot contain NUL")
    return value


def _valid_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ReadAuthorizationError("authorization_key must contain at least 256 bits")
    return key


def _valid_mac(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ReadAuthorizationError("grant mac must be a SHA-256 HMAC hex digest")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ReadAuthorizationError("grant mac must be lowercase hexadecimal")
    return value


def _message(project_id: str, object_id: str, start: int, end: int, nonce: str) -> bytes:
    project = _valid_project_id(project_id)
    oid = _valid_oid(object_id)
    start = _valid_epoch(start, "not_before_epoch")
    end = _valid_epoch(end, "expires_after_epoch")
    if end < start:
        raise ReadAuthorizationError("authorization expiry cannot precede start")
    nonce = _valid_nonce(nonce)
    return (
        b"koschei/read-grant/v1\x00"
        + project.encode("utf-8") + b"\x00"
        + oid.encode("ascii") + b"\x00"
        + str(start).encode("ascii") + b"\x00"
        + str(end).encode("ascii") + b"\x00"
        + nonce.encode("utf-8")
    )


def issue_read_grant(*, project_id: str, object_id: str, not_before_epoch: int,
                     expires_after_epoch: int, nonce: str, authorization_key: bytes) -> ReadGrant:
    key = _valid_key(authorization_key)
    message = _message(project_id, object_id, not_before_epoch, expires_after_epoch, nonce)
    mac = hmac.new(key, message, hashlib.sha256).hexdigest()
    return ReadGrant(
        _valid_project_id(project_id),
        _valid_oid(object_id),
        _valid_epoch(not_before_epoch, "not_before_epoch"),
        _valid_epoch(expires_after_epoch, "expires_after_epoch"),
        _valid_nonce(nonce),
        mac,
    )


def verify_read_grant(grant: ReadGrant, *, project_id: str, object_id: str,
                      epoch: int, authorization_key: bytes) -> bool:
    if not isinstance(grant, ReadGrant):
        return False
    try:
        key = _valid_key(authorization_key)
        project = _valid_project_id(project_id)
        oid = _valid_oid(object_id)
        ep = _valid_epoch(epoch, "epoch")

        grant_project = _valid_project_id(grant.project_id)
        grant_oid = _valid_oid(grant.object_id)
        grant_start = _valid_epoch(grant.not_before_epoch, "grant.not_before_epoch")
        grant_end = _valid_epoch(grant.expires_after_epoch, "grant.expires_after_epoch")
        if grant_end < grant_start:
            return False
        grant_nonce = _valid_nonce(grant.nonce)
        grant_mac = _valid_mac(grant.mac)

        if grant_project != project or grant_oid != oid:
            return False
        if ep < grant_start or ep > grant_end:
            return False
        expected = hmac.new(
            key,
            _message(grant_project, grant_oid, grant_start, grant_end, grant_nonce),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, grant_mac)
    except ReadAuthorizationError:
        return False


def read_with_grant(
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    grant: ReadGrant,
    canonical_reader,
    deception_key: bytes,
    authorization_key: bytes,
    canonical_view_key: bytes | None = None,
) -> SourceView:
    authorized = verify_read_grant(
        grant,
        project_id=project_id,
        object_id=object_id,
        epoch=epoch,
        authorization_key=authorization_key,
    )
    return read_source_view(
        project_id=project_id,
        object_id=object_id,
        epoch=epoch,
        authorized=authorized,
        canonical_reader=canonical_reader,
        deception_key=deception_key,
        canonical_view_key=canonical_view_key,
    )
