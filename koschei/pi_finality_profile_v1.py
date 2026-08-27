"""Pi-specific native verification/finality profile for Koschei Lang v1.

Pi remains outside Koschei Lang core. This module fixes only provider identity and
binds the Pi payment transaction reference to Koschei's generic provider-native
verification + finality bridge.

Current official Pi guidance exposes payment identifiers and transaction ids (`txid`),
but this bootstrap intentionally does not hard-code an unverified response JSON
schema. A trusted Pi adapter supplies the native parser/verifier callback. The entire
successful effect-result bytes are treated as the canonical expected Pi txid bytes.
"""
from __future__ import annotations

from typing import Callable

from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .external_finality_attestation_v1 import ExternalProviderFinalityVerdictV1
from .provider_finality_bridge_v1 import issue_provider_finality_verdict_from_native_receipt_v1
from .provider_native_verifier_v1 import (
    ProviderNativeVerificationReceiptV1,
    ProviderNativeVerificationResultV1,
    verify_provider_native_response_v1,
)

_PROVIDER_ID = "pi"


class PiFinalityProfileV1Error(ValueError):
    pass


def verify_pi_native_payment_response_v1(
    *,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    effect_receipt: EffectExecutionReceiptV1,
    effect_result_txid_bytes: bytes,
    raw_pi_response_bytes: bytes,
    observed_epoch: int,
    verifier: Callable[[bytes], ProviderNativeVerificationResultV1],
    provider_native_verifier_key: bytes,
) -> ProviderNativeVerificationReceiptV1:
    """Verify raw Pi response via trusted adapter and require exact txid-byte binding."""
    try:
        return verify_provider_native_response_v1(
            provider_id=_PROVIDER_ID,
            effect_envelope=effect_envelope,
            effect_receipt=effect_receipt,
            effect_result_bytes=effect_result_txid_bytes,
            raw_response_bytes=raw_pi_response_bytes,
            observed_epoch=observed_epoch,
            verifier=verifier,
            provider_native_verifier_key=provider_native_verifier_key,
        )
    except ValueError as error:
        raise PiFinalityProfileV1Error(str(error)) from error


def issue_pi_finality_verdict_v1(
    *,
    native_receipt: ProviderNativeVerificationReceiptV1,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    effect_receipt: EffectExecutionReceiptV1,
    effect_result_txid_bytes: bytes,
    raw_pi_response_bytes: bytes,
    provider_native_verifier_key: bytes,
    provider_verifier_key: bytes,
) -> ExternalProviderFinalityVerdictV1:
    """Issue Pi finality verdict only from an authenticated Pi-native verification receipt."""
    if native_receipt.provider_id != _PROVIDER_ID:
        raise PiFinalityProfileV1Error("Pi finality requires provider_id=pi")
    try:
        return issue_provider_finality_verdict_from_native_receipt_v1(
            native_receipt=native_receipt,
            effect_envelope=effect_envelope,
            effect_receipt=effect_receipt,
            effect_result_bytes=effect_result_txid_bytes,
            raw_response_bytes=raw_pi_response_bytes,
            provider_native_verifier_key=provider_native_verifier_key,
            provider_verifier_key=provider_verifier_key,
        )
    except ValueError as error:
        raise PiFinalityProfileV1Error(str(error)) from error
