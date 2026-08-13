"""Koschei Event Horizon Isolation v1.

This module is a one-way defensive sink for unauthorized source access.
It deliberately has no canonical-reader callback. Canonical object identity is
consumed only as input to keyed one-way derivation and is never exposed in the
returned envelope. The caller receives a session+epoch scoped synthetic universe
whose identities and source are derived from independent isolation/deception keys.

This is defense-in-depth, not a claim of absolute compromise resistance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from koschei.decoy_view_broker_v1 import generate_decoy_source


class EventHorizonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VoidEnvelope:
    universe_id: str
    shadow_object_id: str
    epoch: int
    provenance: str
    deployable: bool
    content: bytes
    content_sha256: str
    gravity_digest: str


def _require_text(value: str, name: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise EventHorizonError(f"{name} must be non-empty text")
    return value.strip()


def _require_epoch(epoch: int) -> int:
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise EventHorizonError("epoch must be a non-negative integer")
    return epoch


def _require_key(key: bytes, name: str) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise EventHorizonError(f"{name} must contain at least 256 bits")
    return key


def _require_object_id(object_id: str) -> str:
    if not isinstance(object_id, str):
        raise EventHorizonError("object_id must be text")
    oid = object_id.lower()
    if len(oid) < 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise EventHorizonError("object_id must be >=128-bit hexadecimal")
    return oid


def _derive(key: bytes, *, label: bytes, project_id: str, object_id: str,
            session_id: str, epoch: int, previous: bytes = b"") -> bytes:
    message = (
        b"koschei/event-horizon/v1\x00" + label + b"\x00"
        + project_id.encode("utf-8") + b"\x00"
        + object_id.encode("ascii") + b"\x00"
        + session_id.encode("utf-8") + b"\x00"
        + str(epoch).encode("ascii") + b"\x00" + previous
    )
    return hmac.new(key, message, hashlib.sha256).digest()


def enter_event_horizon(*, project_id: str, object_id: str, session_id: str,
                        epoch: int, isolation_key: bytes,
                        deception_key: bytes, depth: int = 7) -> VoidEnvelope:
    """Return a synthetic one-way universe without any canonical read capability."""
    project = _require_text(project_id, "project_id")
    oid = _require_object_id(object_id)
    session = _require_text(session_id, "session_id", minimum=8)
    ep = _require_epoch(epoch)
    iso = _require_key(isolation_key, "isolation_key")
    dec = _require_key(deception_key, "deception_key")
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 3 or depth > 32:
        raise EventHorizonError("depth must be an integer in [3, 32]")

    # A keyed gravity chain intentionally destroys direct structural correspondence.
    state = b""
    for hop in range(depth):
        state = _derive(
            iso,
            label=f"gravity-{hop}".encode("ascii"),
            project_id=project,
            object_id=oid,
            session_id=session,
            epoch=ep,
            previous=state,
        )

    universe_raw = _derive(
        iso, label=b"universe", project_id=project, object_id=oid,
        session_id=session, epoch=ep, previous=state,
    )
    shadow_raw = _derive(
        iso, label=b"shadow-object", project_id=project, object_id=oid,
        session_id=session, epoch=ep, previous=universe_raw,
    )

    universe_id = "void-" + universe_raw.hex()[:32]
    shadow_object_id = shadow_raw.hex()  # valid opaque object id for decoy generation

    # Decoy generation sees only the shadow identity, never the canonical object id.
    content = generate_decoy_source(
        project_id=universe_id,
        object_id=shadow_object_id,
        epoch=ep,
        deception_key=dec,
    )
    content_hash = hashlib.sha256(content).hexdigest()
    gravity_digest = hashlib.sha256(state + universe_raw + shadow_raw).hexdigest()

    return VoidEnvelope(
        universe_id=universe_id,
        shadow_object_id=shadow_object_id,
        epoch=ep,
        provenance="event-horizon-decoy",
        deployable=False,
        content=content,
        content_sha256="sha256:" + content_hash,
        gravity_digest="sha256:" + gravity_digest,
    )


def require_canonical_promotion(_envelope: VoidEnvelope) -> None:
    """Event-horizon material can never be promoted to build/sign/deploy input."""
    raise EventHorizonError("event-horizon material is permanently non-canonical")
