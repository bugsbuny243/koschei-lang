"""Koschei Event Horizon / Void Plane v1.

Defensive isolation boundary for protected source identities.

Security goals:
- unauthorized callers never reach canonical source callbacks;
- no canonical path/filename is accepted or emitted across this boundary;
- unknown and unauthorized object identities collapse to the same void response
  shape, avoiding a simple existence oracle;
- void responses are derived only from independent deception material;
- the public response contains no reverse mapping back to canonical identity.

This is a defense-in-depth layer, not a claim of absolute compromise immunity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable


class EventHorizonError(ValueError):
    pass


CanonicalReader = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class HorizonTicket:
    object_id: str
    epoch: int
    mac: str


@dataclass(frozen=True, slots=True)
class HorizonResponse:
    epoch: int
    zone: str
    deployable: bool
    opaque_locator: str
    payload: bytes
    response_digest: str


def _require_hex_id(value: str) -> str:
    if not isinstance(value, str):
        raise EventHorizonError("object identity must be text")
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise EventHorizonError("object identity must be 256-bit hexadecimal")
    return normalized


def _require_epoch(epoch: int) -> int:
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise EventHorizonError("epoch must be a non-negative integer")
    return epoch


def _require_key(key: bytes, label: str) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise EventHorizonError(f"{label} must contain at least 256 bits")
    return key


def _mac(*, key: bytes, object_id: str, epoch: int) -> str:
    message = b"koschei/event-horizon/v1\x00" + object_id.encode("ascii") + b"\x00" + str(epoch).encode("ascii")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def issue_horizon_ticket(*, object_id: str, epoch: int, authorization_key: bytes) -> HorizonTicket:
    oid = _require_hex_id(object_id)
    ep = _require_epoch(epoch)
    key = _require_key(authorization_key, "authorization_key")
    return HorizonTicket(object_id=oid, epoch=ep, mac=_mac(key=key, object_id=oid, epoch=ep))


def _ticket_valid(*, ticket: HorizonTicket | None, object_id: str, epoch: int, authorization_key: bytes) -> bool:
    if not isinstance(ticket, HorizonTicket):
        return False
    try:
        ticket_oid = _require_hex_id(ticket.object_id)
        ticket_epoch = _require_epoch(ticket.epoch)
    except EventHorizonError:
        return False
    if ticket_oid != object_id or ticket_epoch != epoch:
        return False
    expected = _mac(key=authorization_key, object_id=object_id, epoch=epoch)
    return hmac.compare_digest(ticket.mac, expected)


def _void_material(*, object_id: str, epoch: int, deception_key: bytes) -> tuple[str, bytes]:
    seed = hmac.new(
        deception_key,
        b"koschei/event-horizon/void/v1\x00" + object_id.encode("ascii") + b"\x00" + str(epoch).encode("ascii"),
        hashlib.sha256,
    ).digest()
    locator = "vh_" + hashlib.sha256(seed + b"locator").hexdigest()[:32]
    a = int.from_bytes(hashlib.sha256(seed + b"a").digest()[:2], "big") % 997
    b = int.from_bytes(hashlib.sha256(seed + b"b").digest()[:2], "big") % 997
    payload = (
        f"fn v_{locator[-10:]}(x: Int) -> Int {{\n"
        f"    let y: Int = x * 7 + {a};\n"
        f"    return y + {b};\n"
        f"}}\n"
    ).encode("utf-8")
    return locator, payload


def cross_event_horizon(
    *,
    object_id: str,
    epoch: int,
    ticket: HorizonTicket | None,
    canonical_reader: CanonicalReader,
    authorization_key: bytes,
    deception_key: bytes,
    object_is_known: Callable[[str], bool] | None = None,
) -> HorizonResponse:
    """Resolve one protected read through a non-enumerable defensive boundary.

    Unknown and unauthorized identities deliberately take the same void route.
    The optional object_is_known callback is evaluated only after a valid ticket,
    so unauthenticated callers cannot use this function as an existence oracle.
    """
    oid = _require_hex_id(object_id)
    ep = _require_epoch(epoch)
    auth_key = _require_key(authorization_key, "authorization_key")
    decoy_key = _require_key(deception_key, "deception_key")
    if not callable(canonical_reader):
        raise EventHorizonError("canonical_reader must be callable")
    if object_is_known is not None and not callable(object_is_known):
        raise EventHorizonError("object_is_known must be callable when provided")

    admitted = _ticket_valid(ticket=ticket, object_id=oid, epoch=ep, authorization_key=auth_key)
    if admitted and object_is_known is not None:
        admitted = bool(object_is_known(oid))

    if admitted:
        canonical = canonical_reader(oid)
        if not isinstance(canonical, bytes):
            raise EventHorizonError("canonical_reader must return bytes")
        locator = "ch_" + hashlib.sha256((oid + ":" + str(ep)).encode("ascii")).hexdigest()[:32]
        payload = canonical
        zone = "canonical"
        deployable = True
    else:
        locator, payload = _void_material(object_id=oid, epoch=ep, deception_key=decoy_key)
        zone = "void"
        deployable = False

    return HorizonResponse(
        epoch=ep,
        zone=zone,
        deployable=deployable,
        opaque_locator=locator,
        payload=payload,
        response_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def require_event_horizon_canonical(response: HorizonResponse) -> None:
    if not isinstance(response, HorizonResponse):
        raise EventHorizonError("invalid horizon response")
    if response.zone != "canonical" or response.deployable is not True:
        raise EventHorizonError("void response cannot cross into build/sign/deploy")
