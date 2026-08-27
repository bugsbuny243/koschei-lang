"""Pi-specific provider profile for Koschei external finality attestation v1.

This module does not implement Pi networking, wallet custody, payment settlement, or
blockchain consensus.  It only fixes the provider identity and Pi payment-finality
vocabulary on top of Koschei's generic external finality contract.

A real Pi integration must verify Pi-native transaction/payment state outside this
module and only then invoke the trusted verdict issuer while holding the provider
verifier key.
"""
from __future__ import annotations

from .effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from .external_finality_attestation_v1 import (
    ExternalFinalityAttestationV1Error,
    ExternalProviderFinalityVerdictV1,
    issue_external_provider_finality_verdict_v1,
)

_PROVIDER_ID = "pi"
_PI_STATES = frozenset({"pending", "finalized", "rejected"})


class PiFinalityProfileV1Error(ValueError):
    pass


def issue_pi_finality_verdict_v1(
    *,
    effect_envelope: EffectExecutionProofEnvelopeV1,
    pi_transaction_reference_digest: str,
    pi_provider_proof_digest: str,
    observed_epoch: int,
    state: str,
    provider_verifier_key: bytes,
) -> ExternalProviderFinalityVerdictV1:
    """Issue Pi verdict only after trusted Pi-native verification outside Lang core."""
    if state not in _PI_STATES:
        raise PiFinalityProfileV1Error("unknown Pi finality state")
    try:
        return issue_external_provider_finality_verdict_v1(
            provider_id=_PROVIDER_ID,
            effect_envelope=effect_envelope,
            external_reference_digest=pi_transaction_reference_digest,
            provider_proof_digest=pi_provider_proof_digest,
            observed_epoch=observed_epoch,
            state=state,
            provider_verifier_key=provider_verifier_key,
        )
    except ExternalFinalityAttestationV1Error as error:
        raise PiFinalityProfileV1Error(str(error)) from error
