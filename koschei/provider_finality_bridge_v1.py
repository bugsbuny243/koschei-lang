"""Bridge authenticated provider-native verification into external finality verdicts v1.

The sanctioned path must not let application code choose provider finality state,
external reference, or provider proof after native verification.  This bridge takes
one authenticated ProviderNativeVerificationReceiptV1 and derives those fields into
ExternalProviderFinalityVerdictV1.

The older low-level verdict issuer remains an implementation primitive in the Python
bootstrap, but it is not the sanctioned authoritative path. Native integration must
expose only an equivalent receipt-bound bridge outside the trusted provider verifier
compartment.
"""
from __future__ import annotations

from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1
from .external_finality_attestation_v1 import (
    ExternalProviderFinalityVerdictV1,
    issue_external_provider_finality_verdict_v1,
)
from .provider_native_verifier_v1 import ProviderNativeVerificationReceiptV1


class ProviderFinalityBridgeV1Error(ValueError):
    pass


def issue_provider_finality_verdict_from_native_receipt_v1(
    *,
    native_receipt: ProviderNativeVerificationReceiptV1,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    effect_receipt: EffectExecutionReceiptV1,
    effect_result_bytes: bytes,
    raw_response_bytes: bytes,
    provider_native_verifier_key: bytes,
    provider_verifier_key: bytes,
) -> ExternalProviderFinalityVerdictV1:
    """Derive finality verdict fields exclusively from authenticated native verification."""
    native_receipt.assert_authenticated(
        provider_native_verifier_key=provider_native_verifier_key,
        effect_envelope=effect_envelope,
        effect_receipt=effect_receipt,
        effect_result_bytes=effect_result_bytes,
        raw_response_bytes=raw_response_bytes,
    )
    verdict = issue_external_provider_finality_verdict_v1(
        provider_id=native_receipt.provider_id,
        effect_envelope=effect_envelope,
        external_reference_digest=native_receipt.verified_reference_digest,
        provider_proof_digest=native_receipt.provider_proof_digest,
        observed_epoch=native_receipt.observed_epoch,
        state=native_receipt.state,
        provider_verifier_key=provider_verifier_key,
    )
    if verdict.external_reference_digest != native_receipt.verified_reference_digest:
        raise ProviderFinalityBridgeV1Error("finality verdict reference differs from native receipt")
    if verdict.provider_proof_digest != native_receipt.provider_proof_digest:
        raise ProviderFinalityBridgeV1Error("finality verdict proof differs from native receipt")
    if verdict.state != native_receipt.state:
        raise ProviderFinalityBridgeV1Error("finality verdict state differs from native receipt")
    return verdict
