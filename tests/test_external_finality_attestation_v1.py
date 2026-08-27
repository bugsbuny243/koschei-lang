from dataclasses import replace
import hashlib

import pytest

from koschei.effect_execution_proof_envelope_v1 import EffectExecutionProofEnvelopeV1
from koschei.external_finality_attestation_v1 import (
    ExternalFinalityAttestationV1Error,
    attest_external_finality_v1,
    issue_external_provider_finality_verdict_v1,
)
from koschei.pi_finality_profile_v1 import issue_pi_finality_verdict_v1


def h(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def effect_envelope(*, terminal="effect-completed") -> EffectExecutionProofEnvelopeV1:
    return EffectExecutionProofEnvelopeV1(
        base_execution_envelope_digest=h("base"),
        effect_receipt_digest=h("effect-receipt"),
        canonical_request_digest=h("request"),
        operation="subscription.enable",
        epoch=61,
        terminal_state=terminal,
        measurement_digest=h("effect-measurement"),
        envelope_digest=h("effect-envelope"),
    )


def bundle(*, state="finalized"):
    effect = effect_envelope()
    vk, fk = b"v" * 32, b"f" * 32
    verdict = issue_external_provider_finality_verdict_v1(
        provider_id="pi",
        effect_envelope=effect,
        external_reference_digest=h("pi-tx-61"),
        provider_proof_digest=h("pi-proof-61"),
        observed_epoch=62,
        state=state,
        provider_verifier_key=vk,
    )
    attestation = attest_external_finality_v1(
        effect_envelope=effect,
        verdict=verdict,
        provider_verifier_key=vk,
        finality_key=fk,
    )
    return effect, vk, fk, verdict, attestation


def test_finalized_requires_two_authenticated_trust_roles():
    effect, vk, fk, verdict, attestation = bundle()
    verdict.assert_authenticated(provider_verifier_key=vk, effect_envelope=effect)
    attestation.assert_authenticated(
        provider_verifier_key=vk,
        finality_key=fk,
        effect_envelope=effect,
        verdict=verdict,
    )
    attestation.assert_finalized()
    assert attestation.terminal_state == "provider-finalized"
    assert attestation.authority is False


def test_pending_and_rejected_are_not_finalized():
    for state, terminal in (("pending", "provider-pending"), ("rejected", "provider-rejected")):
        *_, attestation = bundle(state=state)
        assert attestation.terminal_state == terminal
        with pytest.raises(ExternalFinalityAttestationV1Error, match="has not finalized"):
            attestation.assert_finalized()


def test_provider_verdict_cannot_be_issued_from_failed_local_effect():
    with pytest.raises(ExternalFinalityAttestationV1Error, match="locally completed"):
        issue_external_provider_finality_verdict_v1(
            provider_id="pi",
            effect_envelope=effect_envelope(terminal="effect-failed"),
            external_reference_digest=h("tx"),
            provider_proof_digest=h("proof"),
            observed_epoch=62,
            state="finalized",
            provider_verifier_key=b"v" * 32,
        )


def test_finality_observation_cannot_predate_effect_epoch():
    with pytest.raises(ExternalFinalityAttestationV1Error, match="predates effect epoch"):
        issue_external_provider_finality_verdict_v1(
            provider_id="pi",
            effect_envelope=effect_envelope(),
            external_reference_digest=h("tx"),
            provider_proof_digest=h("proof"),
            observed_epoch=60,
            state="finalized",
            provider_verifier_key=b"v" * 32,
        )


def test_verdict_state_or_reference_tampering_breaks_authentication():
    effect, vk, _, verdict, _ = bundle()
    for forged in (
        replace(verdict, state="rejected"),
        replace(verdict, external_reference_digest=h("other-tx")),
        replace(verdict, provider_proof_digest=h("other-proof")),
    ):
        with pytest.raises(ExternalFinalityAttestationV1Error, match="authentication failed"):
            forged.assert_authenticated(provider_verifier_key=vk, effect_envelope=effect)


def test_verdict_cannot_move_to_other_effect_measurement():
    effect, vk, _, verdict, _ = bundle()
    other = replace(effect, measurement_digest=h("other-measurement"))
    with pytest.raises(ExternalFinalityAttestationV1Error, match="measurement mismatch"):
        verdict.assert_authenticated(provider_verifier_key=vk, effect_envelope=other)


def test_wrong_provider_verifier_or_finality_key_rejects():
    effect, vk, fk, verdict, attestation = bundle()
    with pytest.raises(ExternalFinalityAttestationV1Error, match="verdict authentication failed"):
        verdict.assert_authenticated(provider_verifier_key=b"x" * 32, effect_envelope=effect)
    with pytest.raises(ExternalFinalityAttestationV1Error, match="attestation authentication failed"):
        attestation.assert_authenticated(
            provider_verifier_key=vk,
            finality_key=b"x" * 32,
            effect_envelope=effect,
            verdict=verdict,
        )


def test_pi_profile_fixes_provider_identity_without_adding_pi_sdk_to_lang_core():
    effect = effect_envelope()
    verdict = issue_pi_finality_verdict_v1(
        effect_envelope=effect,
        pi_transaction_reference_digest=h("pi-tx"),
        pi_provider_proof_digest=h("pi-proof"),
        observed_epoch=62,
        state="finalized",
        provider_verifier_key=b"v" * 32,
    )
    assert verdict.provider_id == "pi"
