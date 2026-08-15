"""Commercial activation lease, seat binding and revocation for Koschei.

No production signing private key lives here. Activation leases are canonicalized
and verified through an injected verifier. Device binding uses an opaque digest;
the runtime does not need raw hardware serials.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Collection

from .commercial_entitlement_v1 import EntitlementClaims, entitlement_digest, verify_entitlement


class CommercialActivationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivationLease:
    lease_id: str
    customer_id: str
    entitlement_digest: str
    seat_id: str
    device_binding: str
    issued_epoch: int
    online_until_epoch: int
    offline_grace_until_epoch: int
    channel: str


def _nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommercialActivationError(f"{field} must be non-empty text")
    return value.strip()


def _hex64(value: str, field: str) -> str:
    value = _nonempty(value, field).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise CommercialActivationError(f"{field} must be a 32-byte hex digest")
    return value


def _epoch(value: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CommercialActivationError(f"{field} must be a non-negative integer")
    return value


def device_binding_digest(*, customer_id: str, device_public_id: str) -> str:
    customer = _nonempty(customer_id, "customer_id")
    device = _nonempty(device_public_id, "device_public_id")
    payload = b"koschei/device-binding/v1\x00" + customer.encode("utf-8") + b"\x00" + device.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_activation_payload(lease: ActivationLease) -> bytes:
    if not isinstance(lease, ActivationLease):
        raise CommercialActivationError("lease must be ActivationLease")
    issued = _epoch(lease.issued_epoch, "issued_epoch")
    online = _epoch(lease.online_until_epoch, "online_until_epoch")
    grace = _epoch(lease.offline_grace_until_epoch, "offline_grace_until_epoch")
    if online < issued:
        raise CommercialActivationError("online lease expiry cannot precede issue")
    if grace < online:
        raise CommercialActivationError("offline grace cannot end before online lease expiry")
    obj = {
        "schema": "koschei/commercial-activation/v1",
        "lease_id": _nonempty(lease.lease_id, "lease_id"),
        "customer_id": _nonempty(lease.customer_id, "customer_id"),
        "entitlement_digest": _hex64(lease.entitlement_digest, "entitlement_digest"),
        "seat_id": _nonempty(lease.seat_id, "seat_id"),
        "device_binding": _hex64(lease.device_binding, "device_binding"),
        "issued_epoch": issued,
        "online_until_epoch": online,
        "offline_grace_until_epoch": grace,
        "channel": _nonempty(lease.channel, "channel"),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def verify_activation(*, lease: ActivationLease, lease_signature: bytes,
                      lease_verifier: Callable[[bytes, bytes], bool],
                      entitlement: EntitlementClaims, entitlement_signature: bytes,
                      entitlement_verifier: Callable[[bytes, bytes], bool],
                      current_epoch: int, expected_artifact_sha256: str,
                      expected_policy_hash: str, expected_channel: str,
                      expected_device_binding: str, required_feature: str | None = None,
                      revoked_lease_ids: Collection[str] = (),
                      revoked_seat_ids: Collection[str] = (),
                      online: bool = True) -> bool:
    try:
        now = _epoch(current_epoch, "current_epoch")
        expected_channel = _nonempty(expected_channel, "expected_channel")
        expected_binding = _hex64(expected_device_binding, "expected_device_binding")
        payload = canonical_activation_payload(lease)
        if not isinstance(lease_signature, bytes) or not lease_signature:
            return False
        if not bool(lease_verifier(payload, lease_signature)):
            return False
        if lease.lease_id in set(revoked_lease_ids) or lease.seat_id in set(revoked_seat_ids):
            return False
        if lease.channel != expected_channel or entitlement.artifact.channel != expected_channel:
            return False
        if lease.customer_id != entitlement.customer_id:
            return False
        if lease.entitlement_digest != entitlement_digest(entitlement):
            return False
        if lease.device_binding != expected_binding:
            return False
        if now < lease.issued_epoch:
            return False
        deadline = lease.online_until_epoch if online else lease.offline_grace_until_epoch
        if now > deadline:
            return False
        return verify_entitlement(
            claims=entitlement,
            signature=entitlement_signature,
            verifier=entitlement_verifier,
            current_epoch=now,
            expected_artifact_sha256=expected_artifact_sha256,
            expected_policy_hash=expected_policy_hash,
            required_feature=required_feature,
        )
    except (CommercialActivationError, TypeError, ValueError):
        return False
