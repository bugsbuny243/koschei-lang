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


def _valid_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ReadAuthorizationError("authorization_key must contain at least 256 bits")
    return key


def _message(project_id: str, object_id: str, start: int, end: int, nonce: str) -> bytes:
    if not isinstance(project_id, str) or not project_id:
        raise ReadAuthorizationError("project_id must be non-empty text")
    oid = _valid_oid(object_id)
    start = _valid_epoch(start, "not_before_epoch")
    end = _valid_epoch(end, "expires_after_epoch")
    if end < start:
        raise ReadAuthorizationError("authorization expiry cannot precede start")
    if not isinstance(nonce, str) or len(nonce) < 16:
        raise ReadAuthorizationError("nonce must contain at least 16 characters")
    return (
        b"koschei/read-grant/v1\x00"
        + project_id.encode("utf-8") + b"\x00"
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
    return ReadGrant(project_id, _valid_oid(object_id), not_before_epoch, expires_after_epoch, nonce, mac)


def verify_read_grant(grant: ReadGrant, *, project_id: str, object_id: str,
                      epoch: int, authorization_key: bytes) -> bool:
    if not isinstance(grant, ReadGrant):
        return False
    try:
        key = _valid_key(authorization_key)
        oid = _valid_oid(object_id)
        ep = _valid_epoch(epoch, "epoch")
        if grant.project_id != project_id or grant.object_id != oid:
            return False
        if ep < grant.not_before_epoch or ep > grant.expires_after_epoch:
            return False
        expected = hmac.new(
            key,
            _message(grant.project_id, grant.object_id, grant.not_before_epoch,
                     grant.expires_after_epoch, grant.nonce),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, grant.mac)
    except ReadAuthorizationError:
        return False


def read_with_grant(*, project_id: str, object_id: str, epoch: int, grant: ReadGrant,
                    canonical_reader, deception_key: bytes, authorization_key: bytes) -> SourceView:
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
    )
