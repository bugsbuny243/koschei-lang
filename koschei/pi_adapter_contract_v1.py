"""Non-authoritative Pi ecosystem adapter contract for Koschei Lang v1.

This module belongs to Koschei Lang. It does not implement Pi Network, a Pi SDK,
wallet custody, blockchain settlement, or any Web3 subsystem. It defines the
minimum capability-shaped boundary that a future external Pi adapter must satisfy
before Pi identity/payment facts can enter a Koschei execution universe.

The adapter is deliberately non-authoritative: external claims become typed,
scoped evidence. They do not grant ambient disk/network/process authority and
cannot widen Koschei capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

_CTX = b"koschei.pi-adapter-contract/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
_ALLOWED_ACTIONS = frozenset({"identity.verify", "payment.request", "payment.observe"})


class PiAdapterContractError(ValueError):
    pass


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise PiAdapterContractError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise PiAdapterContractError(f"{label} must be hexadecimal")
    if lowered == "0" * 64:
        raise PiAdapterContractError(f"{label} cannot be the zero digest")
    return lowered


def _seal(rows: tuple[str, ...]) -> str:
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PiAdapterCapabilityV1:
    """A least-authority grant describing what an external Pi adapter may ask for."""

    app_id: str
    subject_scope_digest: str
    allowed_actions: tuple[str, ...]
    valid_from_epoch: int
    expires_before_epoch: int
    capability_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if self.authority:
            raise PiAdapterContractError("Pi adapter contract must remain non-authoritative")
        if not isinstance(self.app_id, str) or not self.app_id.strip():
            raise PiAdapterContractError("app_id cannot be empty")
        subject = _require_digest(self.subject_scope_digest, "subject_scope_digest")
        if not isinstance(self.valid_from_epoch, int) or isinstance(self.valid_from_epoch, bool):
            raise PiAdapterContractError("valid_from_epoch must be an integer")
        if not isinstance(self.expires_before_epoch, int) or isinstance(self.expires_before_epoch, bool):
            raise PiAdapterContractError("expires_before_epoch must be an integer")
        if self.valid_from_epoch < 0 or self.expires_before_epoch <= self.valid_from_epoch:
            raise PiAdapterContractError("Pi adapter capability requires a positive epoch lifetime")
        if not self.allowed_actions:
            raise PiAdapterContractError("Pi adapter capability must allow at least one action")
        if tuple(sorted(set(self.allowed_actions))) != self.allowed_actions:
            raise PiAdapterContractError("allowed_actions must be unique and canonically sorted")
        unknown = set(self.allowed_actions) - _ALLOWED_ACTIONS
        if unknown:
            raise PiAdapterContractError("unknown Pi adapter action: " + ", ".join(sorted(unknown)))
        expected = _seal(
            (
                f"app={self.app_id.strip()}",
                f"subject={subject}",
                "actions=" + ",".join(self.allowed_actions),
                f"from={self.valid_from_epoch}",
                f"before={self.expires_before_epoch}",
                "authority=0",
            )
        )
        if self.capability_digest != expected:
            raise PiAdapterContractError("Pi adapter capability seal mismatch")

    def permits(self, action: str, *, current_epoch: int) -> bool:
        self.assert_sealed()
        if not isinstance(current_epoch, int) or isinstance(current_epoch, bool) or current_epoch < 0:
            raise PiAdapterContractError("current_epoch must be a non-negative integer")
        return (
            self.valid_from_epoch <= current_epoch < self.expires_before_epoch
            and action in self.allowed_actions
        )


def issue_pi_adapter_capability_v1(
    *,
    app_id: str,
    subject_scope_digest: str,
    allowed_actions: tuple[str, ...],
    valid_from_epoch: int,
    expires_before_epoch: int,
) -> PiAdapterCapabilityV1:
    """Create a sealed, time-scoped, non-authoritative Pi adapter capability."""

    actions = tuple(sorted(set(allowed_actions)))
    result = PiAdapterCapabilityV1(
        app_id=app_id.strip() if isinstance(app_id, str) else app_id,
        subject_scope_digest=subject_scope_digest,
        allowed_actions=actions,
        valid_from_epoch=valid_from_epoch,
        expires_before_epoch=expires_before_epoch,
        capability_digest="",
    )
    object.__setattr__(
        result,
        "capability_digest",
        _seal(
            (
                f"app={result.app_id}",
                f"subject={_require_digest(result.subject_scope_digest, 'subject_scope_digest')}",
                "actions=" + ",".join(result.allowed_actions),
                f"from={result.valid_from_epoch}",
                f"before={result.expires_before_epoch}",
                "authority=0",
            )
        ),
    )
    result.assert_sealed()
    return result


@dataclass(frozen=True, slots=True)
class PiExternalEvidenceV1:
    """Opaque external evidence admitted through a specific adapter capability."""

    capability_digest: str
    action: str
    external_evidence_digest: str
    observed_epoch: int
    evidence_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self, capability: PiAdapterCapabilityV1) -> None:
        capability.assert_sealed()
        if self.authority:
            raise PiAdapterContractError("Pi external evidence cannot grant Koschei authority")
        if self.capability_digest != capability.capability_digest:
            raise PiAdapterContractError("Pi evidence belongs to a different capability")
        external = _require_digest(self.external_evidence_digest, "external_evidence_digest")
        if not capability.permits(self.action, current_epoch=self.observed_epoch):
            raise PiAdapterContractError("Pi evidence action is outside capability scope or lifetime")
        expected = _seal(
            (
                f"capability={self.capability_digest}",
                f"action={self.action}",
                f"external={external}",
                f"epoch={self.observed_epoch}",
                "authority=0",
            )
        )
        if self.evidence_digest != expected:
            raise PiAdapterContractError("Pi external evidence seal mismatch")


def admit_pi_external_evidence_v1(
    capability: PiAdapterCapabilityV1,
    *,
    action: str,
    external_evidence_digest: str,
    observed_epoch: int,
) -> PiExternalEvidenceV1:
    """Admit an external Pi fact only when a live capability explicitly permits it."""

    capability.assert_sealed()
    external = _require_digest(external_evidence_digest, "external_evidence_digest")
    if not capability.permits(action, current_epoch=observed_epoch):
        raise PiAdapterContractError("Pi adapter action is outside capability scope or lifetime")
    result = PiExternalEvidenceV1(
        capability_digest=capability.capability_digest,
        action=action,
        external_evidence_digest=external,
        observed_epoch=observed_epoch,
        evidence_digest="",
    )
    object.__setattr__(
        result,
        "evidence_digest",
        _seal(
            (
                f"capability={result.capability_digest}",
                f"action={result.action}",
                f"external={result.external_evidence_digest}",
                f"epoch={result.observed_epoch}",
                "authority=0",
            )
        ),
    )
    result.assert_sealed(capability)
    return result
