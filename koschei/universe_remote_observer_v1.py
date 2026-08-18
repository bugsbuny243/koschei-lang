"""Koschei Universe Remote Observer v1.

Produces a signed, authority-free snapshot envelope suitable for mobile/remote
viewers. The observer receives only digests, topology, status and evidence
references; no secret material, capability token, signing key or control-plane
handle is exported.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Mapping

class RemoteObserverError(ValueError): pass

@dataclass(frozen=True, slots=True)
class RemoteObserverEnvelopeV1:
    schema: str
    project: str
    epoch: int
    issued_at_unix: int
    expires_at_unix: int
    payload: Mapping[str, object]
    payload_digest: str
    signature: str
    authority: bool = False

_FORBIDDEN_KEYS = frozenset({
    "secret", "private_key", "private-key", "seed", "mnemonic", "capability",
    "capability_token", "token", "signing_key", "root_material", "plaintext",
})

def _scan_no_sensitive(value: object, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            k=str(key).lower()
            if k in _FORBIDDEN_KEYS:
                raise RemoteObserverError(f"forbidden observer field at {path}.{key}")
            _scan_no_sensitive(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i,item in enumerate(value): _scan_no_sensitive(item, f"{path}[{i}]")

def issue_remote_observer_v1(*, payload: Mapping[str, object], signing_key: bytes,
    issued_at_unix: int, ttl_seconds: int = 60) -> RemoteObserverEnvelopeV1:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise RemoteObserverError("observer signing key must be at least 32 bytes")
    if issued_at_unix < 0 or not (5 <= ttl_seconds <= 300):
        raise RemoteObserverError("observer TTL must be 5..300 seconds")
    if payload.get("authority") is not False:
        raise RemoteObserverError("remote observer payload must be authority-free")
    _scan_no_sensitive(payload)
    project=str(payload.get("project", "")); epoch=payload.get("epoch")
    if not project or not isinstance(epoch, int) or epoch < 0:
        raise RemoteObserverError("canonical project identity and epoch required")
    canonical=json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()
    digest=hashlib.sha3_256(canonical).hexdigest()
    expires=issued_at_unix+ttl_seconds
    signed=b"koschei.universe-remote-observer/v1\x00"+digest.encode()+b"\x00"+str(issued_at_unix).encode()+b"\x00"+str(expires).encode()
    signature=hmac.new(signing_key, signed, hashlib.sha3_256).hexdigest()
    return RemoteObserverEnvelopeV1("koschei.universe-remote-observer/v1", project, epoch,
        issued_at_unix, expires, dict(payload), digest, signature, False)

def verify_remote_observer_v1(envelope: RemoteObserverEnvelopeV1, *, signing_key: bytes,
    now_unix: int) -> bool:
    if not isinstance(envelope, RemoteObserverEnvelopeV1) or envelope.authority:
        return False
    if now_unix < envelope.issued_at_unix or now_unix > envelope.expires_at_unix:
        return False
    try:
        canonical=json.dumps(envelope.payload, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()
    except Exception:
        return False
    digest=hashlib.sha3_256(canonical).hexdigest()
    if not hmac.compare_digest(digest, envelope.payload_digest): return False
    signed=b"koschei.universe-remote-observer/v1\x00"+digest.encode()+b"\x00"+str(envelope.issued_at_unix).encode()+b"\x00"+str(envelope.expires_at_unix).encode()
    expected=hmac.new(signing_key, signed, hashlib.sha3_256).hexdigest()
    return hmac.compare_digest(expected, envelope.signature)
