"""Authenticated external-provider finality provenance for Koschei Lang v1.

Local `effect-completed` is not remote settlement/finality.  This module adds two
separate trust roles after local effect execution:

1. a provider-verifier verdict, authenticated by a provider-verifier key, and
2. a Koschei finality attestation, authenticated by a different finality key.

Neither object carries Koschei authority.  The provider-specific verifier is
responsible for checking the provider-native response/proof and for binding the
external reference it verified to the already-measured local effect chain.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1

_VERDICT_CTX = b"koschei.external-finality-verdict/v1\x00"
_ATTEST_CTX = b"koschei.external-finality-attestation/v1\x00"
_STATES = frozenset({"pending", "finalized", "rejected"})
_TERMINALS = {
    "pending": "provider-pending",
    "finalized": "provider-finalized",
    "rejected": "provider-rejected",
}


class ExternalFinalityAttestationV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalFinalityAttestationV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ExternalFinalityAttestationV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    try:
        int(lowered, 16)
    except ValueError as error:
        raise ExternalFinalityAttestationV1Error(f"{label} must be hexadecimal") from error
    if lowered == "0" * 64:
        raise ExternalFinalityAttestationV1Error(f"{label} cannot be zero")
    return lowered


def _epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExternalFinalityAttestationV1Error(f"{label} must be a non-negative integer")
    return value


def _key(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ExternalFinalityAttestationV1Error(f"{label} must contain at least 32 bytes")
    return value


def _verdict_payload(*, provider_id: str, effect_envelope_digest: str,
                     effect_measurement_digest: str, external_reference_digest: str,
                     provider_proof_digest: str, observed_epoch: int,
                     state: str) -> bytes:
    rows = (
        f"provider={provider_id}",
        f"effect_envelope={effect_envelope_digest}",
        f"effect_measurement={effect_measurement_digest}",
        f"external_reference={external_reference_digest}",
        f"provider_proof={provider_proof_digest}",
        f"observed_epoch={observed_epoch}",
        f"state={state}",
        "authority=0",
    )
    return _VERDICT_CTX + "\n".join(rows).encode("utf-8")


def _attestation_payload(*, verdict_digest: str, provider_id: str,
                         effect_envelope_digest: str,
                         external_reference_digest: str,
                         provider_proof_digest: str,
                         observed_epoch: int, terminal_state: str) -> bytes:
    rows = (
        f"verdict={verdict_digest}",
        f"provider={provider_id}",
        f"effect_envelope={effect_envelope_digest}",
        f"external_reference={external_reference_digest}",
        f"provider_proof={provider_proof_digest}",
        f"observed_epoch={observed_epoch}",
        f"terminal={terminal_state}",
        "authority=0",
    )
    return _ATTEST_CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ExternalProviderFinalityVerdictV1:
    provider_id: str
    effect_execution_envelope_digest: str
    effect_measurement_digest: str
    external_reference_digest: str
    provider_proof_digest: str
    observed_epoch: int
    state: str
    verdict_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, provider_verifier_key: bytes,
                             effect_envelope: EffectExecutionProofEnvelopeV1) -> None:
        key = _key(provider_verifier_key, "provider_verifier_key")
        if self.authority:
            raise ExternalFinalityAttestationV1Error("provider finality verdict cannot carry ambient authority")
        if effect_envelope.authority:
            raise ExternalFinalityAttestationV1Error("effect envelope cannot carry ambient authority")
        if effect_envelope.terminal_state != "effect-completed":
            raise ExternalFinalityAttestationV1Error(
                "provider finality verification requires a locally completed effect"
            )
        provider = _text(self.provider_id, "provider_id")
        effect_digest = _digest(self.effect_execution_envelope_digest, "effect_execution_envelope_digest")
        measurement = _digest(self.effect_measurement_digest, "effect_measurement_digest")
        external_reference = _digest(self.external_reference_digest, "external_reference_digest")
        provider_proof = _digest(self.provider_proof_digest, "provider_proof_digest")
        epoch = _epoch(self.observed_epoch, "observed_epoch")
        state = _text(self.state, "state")
        if state not in _STATES:
            raise ExternalFinalityAttestationV1Error("unknown external provider finality state")
        if effect_digest != effect_envelope.envelope_digest:
            raise ExternalFinalityAttestationV1Error("finality verdict belongs to different effect envelope")
        if measurement != effect_envelope.measurement_digest:
            raise ExternalFinalityAttestationV1Error("finality verdict effect measurement mismatch")
        if epoch < effect_envelope.epoch:
            raise ExternalFinalityAttestationV1Error("provider finality observation predates effect epoch")
        expected = hmac.new(key, _verdict_payload(
            provider_id=provider,
            effect_envelope_digest=effect_digest,
            effect_measurement_digest=measurement,
            external_reference_digest=external_reference,
            provider_proof_digest=provider_proof,
            observed_epoch=epoch,
            state=state,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.verdict_digest, expected):
            raise ExternalFinalityAttestationV1Error("provider finality verdict authentication failed")


def issue_external_provider_finality_verdict_v1(
    *,
    provider_id: str,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    external_reference_digest: str,
    provider_proof_digest: str,
    observed_epoch: int,
    state: str,
    provider_verifier_key: bytes,
) -> ExternalProviderFinalityVerdictV1:
    """Trusted verifier issuer; provider-specific code must call this only after native verification."""
    key = _key(provider_verifier_key, "provider_verifier_key")
    provider = _text(provider_id, "provider_id")
    external_reference = _digest(external_reference_digest, "external_reference_digest")
    provider_proof = _digest(provider_proof_digest, "provider_proof_digest")
    epoch = _epoch(observed_epoch, "observed_epoch")
    state = _text(state, "state")
    if state not in _STATES:
        raise ExternalFinalityAttestationV1Error("unknown external provider finality state")
    if effect_envelope.authority or effect_envelope.terminal_state != "effect-completed":
        raise ExternalFinalityAttestationV1Error(
            "provider finality verification requires a non-authoritative effect-completed envelope"
        )
    if epoch < effect_envelope.epoch:
        raise ExternalFinalityAttestationV1Error("provider finality observation predates effect epoch")
    result = ExternalProviderFinalityVerdictV1(
        provider_id=provider,
        effect_execution_envelope_digest=effect_envelope.envelope_digest,
        effect_measurement_digest=effect_envelope.measurement_digest,
        external_reference_digest=external_reference,
        provider_proof_digest=provider_proof,
        observed_epoch=epoch,
        state=state,
        verdict_digest="",
    )
    mac = hmac.new(key, _verdict_payload(
        provider_id=result.provider_id,
        effect_envelope_digest=result.effect_execution_envelope_digest,
        effect_measurement_digest=result.effect_measurement_digest,
        external_reference_digest=result.external_reference_digest,
        provider_proof_digest=result.provider_proof_digest,
        observed_epoch=result.observed_epoch,
        state=result.state,
    ), hashlib.sha256).hexdigest()
    object.__setattr__(result, "verdict_digest", mac)
    result.assert_authenticated(provider_verifier_key=key, effect_envelope=effect_envelope)
    return result


@dataclass(frozen=True, slots=True)
class ExternalFinalityAttestationV1:
    provider_verdict_digest: str
    provider_id: str
    effect_execution_envelope_digest: str
    external_reference_digest: str
    provider_proof_digest: str
    observed_epoch: int
    terminal_state: str
    attestation_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, provider_verifier_key: bytes,
                             finality_key: bytes,
                             effect_envelope: EffectExecutionProofEnvelopeV1,
                             verdict: ExternalProviderFinalityVerdictV1) -> None:
        key = _key(finality_key, "finality_key")
        if self.authority:
            raise ExternalFinalityAttestationV1Error("finality attestation cannot carry ambient authority")
        verdict.assert_authenticated(
            provider_verifier_key=provider_verifier_key,
            effect_envelope=effect_envelope,
        )
        expected_terminal = _TERMINALS[verdict.state]
        expected_fields = (
            (self.provider_verdict_digest, verdict.verdict_digest, "provider verdict"),
            (self.provider_id, verdict.provider_id, "provider"),
            (self.effect_execution_envelope_digest, effect_envelope.envelope_digest, "effect envelope"),
            (self.external_reference_digest, verdict.external_reference_digest, "external reference"),
            (self.provider_proof_digest, verdict.provider_proof_digest, "provider proof"),
            (self.observed_epoch, verdict.observed_epoch, "observed epoch"),
            (self.terminal_state, expected_terminal, "terminal state"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise ExternalFinalityAttestationV1Error(f"finality attestation {label} mismatch")
        expected = hmac.new(key, _attestation_payload(
            verdict_digest=self.provider_verdict_digest,
            provider_id=self.provider_id,
            effect_envelope_digest=self.effect_execution_envelope_digest,
            external_reference_digest=self.external_reference_digest,
            provider_proof_digest=self.provider_proof_digest,
            observed_epoch=self.observed_epoch,
            terminal_state=self.terminal_state,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.attestation_digest, expected):
            raise ExternalFinalityAttestationV1Error("external finality attestation authentication failed")

    def assert_finalized(self) -> None:
        if self.terminal_state != "provider-finalized":
            raise ExternalFinalityAttestationV1Error("external provider has not finalized this effect")


def attest_external_finality_v1(
    *,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    verdict: ExternalProviderFinalityVerdictV1,
    provider_verifier_key: bytes,
    finality_key: bytes,
) -> ExternalFinalityAttestationV1:
    """Authenticate provider-verifier output as Koschei finality provenance, never authority."""
    key = _key(finality_key, "finality_key")
    verdict.assert_authenticated(
        provider_verifier_key=provider_verifier_key,
        effect_envelope=effect_envelope,
    )
    result = ExternalFinalityAttestationV1(
        provider_verdict_digest=verdict.verdict_digest,
        provider_id=verdict.provider_id,
        effect_execution_envelope_digest=effect_envelope.envelope_digest,
        external_reference_digest=verdict.external_reference_digest,
        provider_proof_digest=verdict.provider_proof_digest,
        observed_epoch=verdict.observed_epoch,
        terminal_state=_TERMINALS[verdict.state],
        attestation_digest="",
    )
    mac = hmac.new(key, _attestation_payload(
        verdict_digest=result.provider_verdict_digest,
        provider_id=result.provider_id,
        effect_envelope_digest=result.effect_execution_envelope_digest,
        external_reference_digest=result.external_reference_digest,
        provider_proof_digest=result.provider_proof_digest,
        observed_epoch=result.observed_epoch,
        terminal_state=result.terminal_state,
    ), hashlib.sha256).hexdigest()
    object.__setattr__(result, "attestation_digest", mac)
    result.assert_authenticated(
        provider_verifier_key=provider_verifier_key,
        finality_key=key,
        effect_envelope=effect_envelope,
        verdict=verdict,
    )
    return result
