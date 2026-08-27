"""Provider-native raw-response verification boundary for Koschei Lang v1.

This layer closes the gap between an opaque provider response and the authenticated
ExternalProviderFinalityVerdictV1 used later in the finality chain.

V1 deliberately does not parse provider JSON in generic Lang core. A trusted
provider-specific verifier callback receives raw response bytes and must return a
canonical reference plus canonical proof bytes and one of pending/finalized/rejected.
The runtime binds that result to the exact locally measured effect-result bytes.

For V1 the entire successful effect-result byte string is the expected external
reference. Provider profiles that need richer result payloads must define a later
canonical extraction contract instead of silently parsing ad-hoc representations.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable

from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1

_CTX = b"koschei.provider-native-verifier/v1\x00"
_RAW_CTX = b"koschei.provider-native-raw-response/v1\x00"
_REF_CTX = b"koschei.provider-native-reference/v1\x00"
_PROOF_CTX = b"koschei.provider-native-proof/v1\x00"
_STATES = frozenset({"pending", "finalized", "rejected"})


class ProviderNativeVerifierV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ProviderNativeVerifierV1Error("provider_native_verifier_key must contain at least 32 bytes")
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderNativeVerifierV1Error(f"{label} cannot be empty")
    return value.strip()


def _epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProviderNativeVerifierV1Error("observed_epoch must be a non-negative integer")
    return value


def _hash(ctx: bytes, value: bytes, label: str) -> str:
    if not isinstance(value, bytes) or not value:
        raise ProviderNativeVerifierV1Error(f"{label} must be non-empty bytes")
    return hashlib.sha256(ctx + value).hexdigest()


def _payload(*, provider_id: str, effect_envelope_digest: str,
             effect_receipt_digest: str, effect_measurement_digest: str,
             raw_response_digest: str, expected_reference_digest: str,
             verified_reference_digest: str, provider_proof_digest: str,
             observed_epoch: int, state: str) -> bytes:
    rows = (
        f"provider={provider_id}",
        f"effect_envelope={effect_envelope_digest}",
        f"effect_receipt={effect_receipt_digest}",
        f"effect_measurement={effect_measurement_digest}",
        f"raw_response={raw_response_digest}",
        f"expected_reference={expected_reference_digest}",
        f"verified_reference={verified_reference_digest}",
        f"provider_proof={provider_proof_digest}",
        f"observed_epoch={observed_epoch}",
        f"state={state}",
        "authority=0",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ProviderNativeVerificationResultV1:
    """Trusted provider adapter output before Koschei authenticates the observation."""

    reference_bytes: bytes
    proof_bytes: bytes
    state: str


@dataclass(frozen=True, slots=True)
class ProviderNativeVerificationReceiptV1:
    provider_id: str
    effect_execution_envelope_digest: str
    effect_receipt_digest: str
    effect_measurement_digest: str
    raw_response_digest: str
    expected_reference_digest: str
    verified_reference_digest: str
    provider_proof_digest: str
    observed_epoch: int
    state: str
    receipt_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(
        self,
        *,
        provider_native_verifier_key: bytes,
        effect_envelope: EffectExecutionProofEnvelopeV1,
        effect_receipt: EffectExecutionReceiptV1,
        effect_result_bytes: bytes,
        raw_response_bytes: bytes,
    ) -> None:
        key = _key(provider_native_verifier_key)
        if self.authority:
            raise ProviderNativeVerifierV1Error("provider-native verification receipt cannot carry ambient authority")
        if effect_envelope.terminal_state != "effect-completed":
            raise ProviderNativeVerifierV1Error("provider-native verification requires effect-completed")
        effect_receipt.assert_completed_result(effect_result_bytes)
        if self.effect_execution_envelope_digest != effect_envelope.envelope_digest:
            raise ProviderNativeVerifierV1Error("provider-native receipt effect envelope mismatch")
        if self.effect_receipt_digest != effect_envelope.effect_receipt_digest:
            raise ProviderNativeVerifierV1Error("provider-native receipt effect receipt mismatch")
        if self.effect_measurement_digest != effect_envelope.measurement_digest:
            raise ProviderNativeVerifierV1Error("provider-native receipt effect measurement mismatch")
        expected_reference = _hash(_REF_CTX, effect_result_bytes, "effect_result_bytes")
        if self.expected_reference_digest != expected_reference:
            raise ProviderNativeVerifierV1Error("provider-native expected reference mismatch")
        if self.verified_reference_digest != expected_reference:
            raise ProviderNativeVerifierV1Error("provider-native verified reference differs from effect result")
        raw_digest = _hash(_RAW_CTX, raw_response_bytes, "raw_response_bytes")
        if self.raw_response_digest != raw_digest:
            raise ProviderNativeVerifierV1Error("provider-native raw response mismatch")
        if self.state not in _STATES:
            raise ProviderNativeVerifierV1Error("unknown provider-native verification state")
        epoch = _epoch(self.observed_epoch)
        if epoch < effect_envelope.epoch:
            raise ProviderNativeVerifierV1Error("provider-native observation predates effect epoch")
        expected = hmac.new(
            key,
            _payload(
                provider_id=_text(self.provider_id, "provider_id"),
                effect_envelope_digest=self.effect_execution_envelope_digest,
                effect_receipt_digest=self.effect_receipt_digest,
                effect_measurement_digest=self.effect_measurement_digest,
                raw_response_digest=self.raw_response_digest,
                expected_reference_digest=self.expected_reference_digest,
                verified_reference_digest=self.verified_reference_digest,
                provider_proof_digest=self.provider_proof_digest,
                observed_epoch=epoch,
                state=self.state,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(self.receipt_digest, expected):
            raise ProviderNativeVerifierV1Error("provider-native verification receipt authentication failed")


def verify_provider_native_response_v1(
    *,
    provider_id: str,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    effect_receipt: EffectExecutionReceiptV1,
    effect_result_bytes: bytes,
    raw_response_bytes: bytes,
    observed_epoch: int,
    verifier: Callable[[bytes], ProviderNativeVerificationResultV1],
    provider_native_verifier_key: bytes,
) -> ProviderNativeVerificationReceiptV1:
    """Invoke trusted provider verifier over raw bytes and bind its result to local effect bytes."""
    key = _key(provider_native_verifier_key)
    provider = _text(provider_id, "provider_id")
    epoch = _epoch(observed_epoch)
    if effect_envelope.terminal_state != "effect-completed":
        raise ProviderNativeVerifierV1Error("provider-native verification requires effect-completed")
    effect_receipt.assert_completed_result(effect_result_bytes)
    if not callable(verifier):
        raise ProviderNativeVerifierV1Error("provider-native verifier must be callable")
    raw_digest = _hash(_RAW_CTX, raw_response_bytes, "raw_response_bytes")
    expected_reference = _hash(_REF_CTX, effect_result_bytes, "effect_result_bytes")
    if epoch < effect_envelope.epoch:
        raise ProviderNativeVerifierV1Error("provider-native observation predates effect epoch")

    result = verifier(raw_response_bytes)
    if not isinstance(result, ProviderNativeVerificationResultV1):
        raise ProviderNativeVerifierV1Error("provider-native verifier returned invalid result type")
    state = _text(result.state, "state")
    if state not in _STATES:
        raise ProviderNativeVerifierV1Error("unknown provider-native verification state")
    verified_reference = _hash(_REF_CTX, result.reference_bytes, "verified reference")
    if verified_reference != expected_reference:
        raise ProviderNativeVerifierV1Error("provider-native verified reference differs from effect result")
    provider_proof = _hash(_PROOF_CTX, result.proof_bytes, "provider proof")

    receipt = ProviderNativeVerificationReceiptV1(
        provider_id=provider,
        effect_execution_envelope_digest=effect_envelope.envelope_digest,
        effect_receipt_digest=effect_envelope.effect_receipt_digest,
        effect_measurement_digest=effect_envelope.measurement_digest,
        raw_response_digest=raw_digest,
        expected_reference_digest=expected_reference,
        verified_reference_digest=verified_reference,
        provider_proof_digest=provider_proof,
        observed_epoch=epoch,
        state=state,
        receipt_digest="",
    )
    mac = hmac.new(
        key,
        _payload(
            provider_id=receipt.provider_id,
            effect_envelope_digest=receipt.effect_execution_envelope_digest,
            effect_receipt_digest=receipt.effect_receipt_digest,
            effect_measurement_digest=receipt.effect_measurement_digest,
            raw_response_digest=receipt.raw_response_digest,
            expected_reference_digest=receipt.expected_reference_digest,
            verified_reference_digest=receipt.verified_reference_digest,
            provider_proof_digest=receipt.provider_proof_digest,
            observed_epoch=receipt.observed_epoch,
            state=receipt.state,
        ),
        hashlib.sha256,
    ).hexdigest()
    object.__setattr__(receipt, "receipt_digest", mac)
    receipt.assert_authenticated(
        provider_native_verifier_key=key,
        effect_envelope=effect_envelope,
        effect_receipt=effect_receipt,
        effect_result_bytes=effect_result_bytes,
        raw_response_bytes=raw_response_bytes,
    )
    return receipt
