"""Generic non-authoritative external adapter contract for Koschei Lang v1.

External systems may report identity, payment, cloud, banking, chain, or other
facts, but those facts are not Koschei authority. This module defines the common
least-authority grant and evidence admission physics shared by ecosystem-specific
adapters. Provider-specific semantics and SDK behavior remain outside this core.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import string

_CTX = b"koschei.external-adapter-contract/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class ExternalAdapterContractError(ValueError):
    pass


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalAdapterContractError(f"{label} cannot be empty")
    return value.strip()


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ExternalAdapterContractError(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise ExternalAdapterContractError(f"{label} must be hexadecimal")
    if lowered == "0" * 64:
        raise ExternalAdapterContractError(f"{label} cannot be the zero digest")
    return lowered


def _require_epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExternalAdapterContractError(f"{label} must be a non-negative integer")
    return value


def _canonical_actions(actions: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(actions, tuple) or not actions:
        raise ExternalAdapterContractError("allowed_actions must contain at least one action")
    cleaned = tuple(_require_text(action, "adapter action") for action in actions)
    canonical = tuple(sorted(set(cleaned)))
    if canonical != actions:
        raise ExternalAdapterContractError("allowed_actions must be unique and canonically sorted")
    return canonical


def _seal(rows: tuple[str, ...]) -> str:
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalAdapterGrantV1:
    """Time-scoped permission for one provider to report bounded external facts."""

    provider_id: str
    consumer_id: str
    subject_scope_digest: str
    allowed_actions: tuple[str, ...]
    valid_from_epoch: int
    expires_before_epoch: int
    grant_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self) -> None:
        if self.authority:
            raise ExternalAdapterContractError("external adapter grants cannot carry Koschei authority")
        provider = _require_text(self.provider_id, "provider_id")
        consumer = _require_text(self.consumer_id, "consumer_id")
        subject = _require_digest(self.subject_scope_digest, "subject_scope_digest")
        actions = _canonical_actions(self.allowed_actions)
        start = _require_epoch(self.valid_from_epoch, "valid_from_epoch")
        expiry = _require_epoch(self.expires_before_epoch, "expires_before_epoch")
        if expiry <= start:
            raise ExternalAdapterContractError("external adapter grant requires a positive epoch lifetime")
        expected = _seal((
            f"provider={provider}",
            f"consumer={consumer}",
            f"subject={subject}",
            "actions=" + ",".join(actions),
            f"from={start}",
            f"before={expiry}",
            "authority=0",
        ))
        if self.grant_digest != expected:
            raise ExternalAdapterContractError("external adapter grant seal mismatch")

    def permits(self, action: str, *, current_epoch: int) -> bool:
        self.assert_sealed()
        action = _require_text(action, "action")
        epoch = _require_epoch(current_epoch, "current_epoch")
        return self.valid_from_epoch <= epoch < self.expires_before_epoch and action in self.allowed_actions


def issue_external_adapter_grant_v1(
    *,
    provider_id: str,
    consumer_id: str,
    subject_scope_digest: str,
    allowed_actions: tuple[str, ...],
    valid_from_epoch: int,
    expires_before_epoch: int,
) -> ExternalAdapterGrantV1:
    provider = _require_text(provider_id, "provider_id")
    consumer = _require_text(consumer_id, "consumer_id")
    subject = _require_digest(subject_scope_digest, "subject_scope_digest")
    actions = tuple(sorted(set(_require_text(action, "adapter action") for action in allowed_actions)))
    start = _require_epoch(valid_from_epoch, "valid_from_epoch")
    expiry = _require_epoch(expires_before_epoch, "expires_before_epoch")
    if not actions:
        raise ExternalAdapterContractError("allowed_actions must contain at least one action")
    if expiry <= start:
        raise ExternalAdapterContractError("external adapter grant requires a positive epoch lifetime")
    result = ExternalAdapterGrantV1(provider, consumer, subject, actions, start, expiry, "")
    object.__setattr__(result, "grant_digest", _seal((
        f"provider={provider}",
        f"consumer={consumer}",
        f"subject={subject}",
        "actions=" + ",".join(actions),
        f"from={start}",
        f"before={expiry}",
        "authority=0",
    )))
    result.assert_sealed()
    return result


@dataclass(frozen=True, slots=True)
class ExternalAdapterEvidenceV1:
    """Opaque external evidence bound to exactly one external adapter grant."""

    grant_digest: str
    provider_id: str
    action: str
    external_evidence_digest: str
    observed_epoch: int
    evidence_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self, grant: ExternalAdapterGrantV1) -> None:
        grant.assert_sealed()
        if self.authority:
            raise ExternalAdapterContractError("external evidence cannot grant Koschei authority")
        if self.grant_digest != grant.grant_digest:
            raise ExternalAdapterContractError("external evidence belongs to a different grant")
        provider = _require_text(self.provider_id, "provider_id")
        if provider != grant.provider_id:
            raise ExternalAdapterContractError("external evidence provider does not match grant")
        external = _require_digest(self.external_evidence_digest, "external_evidence_digest")
        epoch = _require_epoch(self.observed_epoch, "observed_epoch")
        action = _require_text(self.action, "action")
        if not grant.permits(action, current_epoch=epoch):
            raise ExternalAdapterContractError("external evidence action is outside grant scope or lifetime")
        expected = _seal((
            f"grant={self.grant_digest}",
            f"provider={provider}",
            f"action={action}",
            f"external={external}",
            f"epoch={epoch}",
            "authority=0",
        ))
        if self.evidence_digest != expected:
            raise ExternalAdapterContractError("external adapter evidence seal mismatch")


def admit_external_adapter_evidence_v1(
    grant: ExternalAdapterGrantV1,
    *,
    action: str,
    external_evidence_digest: str,
    observed_epoch: int,
) -> ExternalAdapterEvidenceV1:
    grant.assert_sealed()
    action = _require_text(action, "action")
    external = _require_digest(external_evidence_digest, "external_evidence_digest")
    epoch = _require_epoch(observed_epoch, "observed_epoch")
    if not grant.permits(action, current_epoch=epoch):
        raise ExternalAdapterContractError("external adapter action is outside grant scope or lifetime")
    result = ExternalAdapterEvidenceV1(grant.grant_digest, grant.provider_id, action, external, epoch, "")
    object.__setattr__(result, "evidence_digest", _seal((
        f"grant={result.grant_digest}",
        f"provider={result.provider_id}",
        f"action={result.action}",
        f"external={result.external_evidence_digest}",
        f"epoch={result.observed_epoch}",
        "authority=0",
    )))
    result.assert_sealed(grant)
    return result
