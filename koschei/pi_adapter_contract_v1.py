"""Non-authoritative Pi ecosystem adapter contract for Koschei Lang v1.

Pi remains an external ecosystem. This module owns only the Pi-specific action
vocabulary and maps it onto Koschei's generic external adapter grant/evidence
physics. Pi SDK behavior, wallet custody, settlement, networking, and Web3 logic
remain outside Koschei Lang.
"""
from __future__ import annotations

from dataclasses import dataclass

from .external_adapter_contract_v1 import (
    ExternalAdapterContractError,
    ExternalAdapterEvidenceV1,
    ExternalAdapterGrantV1,
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)

_PROVIDER_ID = "pi"
_ALLOWED_ACTIONS = frozenset({"identity.verify", "payment.request", "payment.observe"})


class PiAdapterContractError(ValueError):
    pass


def _translate_error(exc: ExternalAdapterContractError) -> PiAdapterContractError:
    return PiAdapterContractError(str(exc))


def _require_pi_actions(actions: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(actions, tuple) or not actions:
        raise PiAdapterContractError("Pi adapter capability must allow at least one action")
    canonical = tuple(sorted(set(actions)))
    if canonical != actions:
        raise PiAdapterContractError("allowed_actions must be unique and canonically sorted")
    unknown = set(actions) - _ALLOWED_ACTIONS
    if unknown:
        raise PiAdapterContractError("unknown Pi adapter action: " + ", ".join(sorted(unknown)))
    return actions


@dataclass(frozen=True, slots=True)
class PiAdapterCapabilityV1:
    """Pi-specific view of a generic non-authoritative external adapter grant."""

    app_id: str
    subject_scope_digest: str
    allowed_actions: tuple[str, ...]
    valid_from_epoch: int
    expires_before_epoch: int
    capability_digest: str
    authority: bool = False
    version: int = 1

    def _as_external_grant(self) -> ExternalAdapterGrantV1:
        return ExternalAdapterGrantV1(
            provider_id=_PROVIDER_ID,
            consumer_id=self.app_id,
            subject_scope_digest=self.subject_scope_digest,
            allowed_actions=self.allowed_actions,
            valid_from_epoch=self.valid_from_epoch,
            expires_before_epoch=self.expires_before_epoch,
            grant_digest=self.capability_digest,
            authority=self.authority,
        )

    def assert_sealed(self) -> None:
        _require_pi_actions(self.allowed_actions)
        try:
            self._as_external_grant().assert_sealed()
        except ExternalAdapterContractError as exc:
            raise _translate_error(exc) from exc

    def permits(self, action: str, *, current_epoch: int) -> bool:
        self.assert_sealed()
        if action not in _ALLOWED_ACTIONS:
            return False
        try:
            return self._as_external_grant().permits(action, current_epoch=current_epoch)
        except ExternalAdapterContractError as exc:
            raise _translate_error(exc) from exc


def issue_pi_adapter_capability_v1(
    *,
    app_id: str,
    subject_scope_digest: str,
    allowed_actions: tuple[str, ...],
    valid_from_epoch: int,
    expires_before_epoch: int,
) -> PiAdapterCapabilityV1:
    """Issue a Pi-specific capability using generic external adapter grant physics."""

    actions = tuple(sorted(set(allowed_actions)))
    _require_pi_actions(actions)
    try:
        grant = issue_external_adapter_grant_v1(
            provider_id=_PROVIDER_ID,
            consumer_id=app_id,
            subject_scope_digest=subject_scope_digest,
            allowed_actions=actions,
            valid_from_epoch=valid_from_epoch,
            expires_before_epoch=expires_before_epoch,
        )
    except ExternalAdapterContractError as exc:
        raise _translate_error(exc) from exc
    result = PiAdapterCapabilityV1(
        app_id=grant.consumer_id,
        subject_scope_digest=grant.subject_scope_digest,
        allowed_actions=grant.allowed_actions,
        valid_from_epoch=grant.valid_from_epoch,
        expires_before_epoch=grant.expires_before_epoch,
        capability_digest=grant.grant_digest,
    )
    result.assert_sealed()
    return result


@dataclass(frozen=True, slots=True)
class PiExternalEvidenceV1:
    """Pi-specific view of generic external evidence admitted under one capability."""

    capability_digest: str
    action: str
    external_evidence_digest: str
    observed_epoch: int
    evidence_digest: str
    authority: bool = False
    version: int = 1

    def _as_external_evidence(self) -> ExternalAdapterEvidenceV1:
        return ExternalAdapterEvidenceV1(
            grant_digest=self.capability_digest,
            provider_id=_PROVIDER_ID,
            action=self.action,
            external_evidence_digest=self.external_evidence_digest,
            observed_epoch=self.observed_epoch,
            evidence_digest=self.evidence_digest,
            authority=self.authority,
        )

    def assert_sealed(self, capability: PiAdapterCapabilityV1) -> None:
        capability.assert_sealed()
        if self.action not in _ALLOWED_ACTIONS:
            raise PiAdapterContractError("unknown Pi adapter action: " + self.action)
        try:
            self._as_external_evidence().assert_sealed(capability._as_external_grant())
        except ExternalAdapterContractError as exc:
            raise _translate_error(exc) from exc


def admit_pi_external_evidence_v1(
    capability: PiAdapterCapabilityV1,
    *,
    action: str,
    external_evidence_digest: str,
    observed_epoch: int,
) -> PiExternalEvidenceV1:
    """Admit Pi evidence only through its Pi whitelist and generic grant boundary."""

    capability.assert_sealed()
    if action not in _ALLOWED_ACTIONS:
        raise PiAdapterContractError("unknown Pi adapter action: " + action)
    try:
        evidence = admit_external_adapter_evidence_v1(
            capability._as_external_grant(),
            action=action,
            external_evidence_digest=external_evidence_digest,
            observed_epoch=observed_epoch,
        )
    except ExternalAdapterContractError as exc:
        raise _translate_error(exc) from exc
    result = PiExternalEvidenceV1(
        capability_digest=evidence.grant_digest,
        action=evidence.action,
        external_evidence_digest=evidence.external_evidence_digest,
        observed_epoch=evidence.observed_epoch,
        evidence_digest=evidence.evidence_digest,
    )
    result.assert_sealed(capability)
    return result
