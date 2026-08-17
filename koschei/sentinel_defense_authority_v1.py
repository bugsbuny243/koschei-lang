"""Bounded Sentinel defense authority for the Koschei reality fabric."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from typing import Callable, Literal

DefenseAction = Literal["quarantine", "revoke", "tighten", "canary", "rollback"]
_ALLOWED = frozenset({"quarantine", "revoke", "tighten", "canary", "rollback"})
_CONTEXT = b"koschei.sentinel-defense-authority/v1\x00"

class SentinelDefenseAuthorityError(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class SentinelDefenseAuthorityV1:
    project_commitment: bytes
    epoch: int
    actions: frozenset[str]
    not_before: int
    expires_at: int
    max_actions: int
    delegation_digest: bytes

    def __repr__(self) -> str:
        return ("SentinelDefenseAuthorityV1(project=<committed>, epoch="
                f"{self.epoch}, actions={sorted(self.actions)!r}, window=<bounded>, "
                f"max_actions={self.max_actions}, delegation=<redacted>)")

@dataclass(frozen=True, slots=True)
class SentinelDefenseRequestV1:
    action: DefenseAction
    project_commitment: bytes
    epoch: int
    target_commitment: bytes
    reason_digest: bytes
    delegation_digest: bytes

    def __repr__(self) -> str:
        return (f"SentinelDefenseRequestV1(action={self.action!r}, project=<committed>, "
                f"epoch={self.epoch}, target=<committed>, reason=<redacted>)")

def _digest(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise SentinelDefenseAuthorityError(f"{label} must be exactly 32 bytes")
    return value

def issue_sentinel_defense_authority_v1(*, project_commitment: bytes, epoch: int,
        actions: frozenset[str], not_before: int, expires_at: int,
        max_actions: int, host_nonce: bytes) -> SentinelDefenseAuthorityV1:
    project = _digest(project_commitment, "project commitment")
    nonce = _digest(host_nonce, "host nonce")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        raise SentinelDefenseAuthorityError("epoch must be positive")
    if not actions or not actions.issubset(_ALLOWED):
        raise SentinelDefenseAuthorityError("unsupported or empty defense action set")
    if not isinstance(not_before, int) or not isinstance(expires_at, int) or expires_at <= not_before:
        raise SentinelDefenseAuthorityError("invalid defense authority window")
    if expires_at - not_before > 3600:
        raise SentinelDefenseAuthorityError("defense authority window exceeds one hour")
    if not isinstance(max_actions, int) or isinstance(max_actions, bool) or not 1 <= max_actions <= 64:
        raise SentinelDefenseAuthorityError("max_actions must be in 1..64")
    payload = b"\x00".join((project, epoch.to_bytes(8, "big"),
        b",".join(sorted(a.encode("ascii") for a in actions)),
        not_before.to_bytes(8, "big"), expires_at.to_bytes(8, "big"),
        max_actions.to_bytes(2, "big"), nonce))
    delegation = hashlib.sha3_256(_CONTEXT + payload).digest()
    return SentinelDefenseAuthorityV1(project, epoch, frozenset(actions), not_before,
        expires_at, max_actions, delegation)

def authorize_sentinel_defense_request_v1(authority: SentinelDefenseAuthorityV1, *,
        action: DefenseAction, target_commitment: bytes, reason_digest: bytes,
        now: int) -> SentinelDefenseRequestV1:
    if not isinstance(authority, SentinelDefenseAuthorityV1):
        raise SentinelDefenseAuthorityError("canonical Sentinel defense authority required")
    if action not in _ALLOWED or action not in authority.actions:
        raise SentinelDefenseAuthorityError("defense action is outside delegated authority")
    if not isinstance(now, int) or now < authority.not_before or now >= authority.expires_at:
        raise SentinelDefenseAuthorityError("defense authority is not active")
    return SentinelDefenseRequestV1(action, authority.project_commitment, authority.epoch,
        _digest(target_commitment, "target commitment"),
        _digest(reason_digest, "reason digest"), authority.delegation_digest)

def execute_sentinel_defense_request_v1(request: SentinelDefenseRequestV1, *,
        enforcer: Callable[[SentinelDefenseRequestV1], bool]) -> bool:
    if not isinstance(request, SentinelDefenseRequestV1):
        raise SentinelDefenseAuthorityError("canonical defense request required")
    if not callable(enforcer):
        raise SentinelDefenseAuthorityError("trusted defense enforcer required")
    try:
        result = enforcer(request)
    except Exception:
        raise SentinelDefenseAuthorityError("defense enforcement failed") from None
    if not isinstance(result, bool):
        raise SentinelDefenseAuthorityError("defense enforcer returned non-canonical result")
    return result
