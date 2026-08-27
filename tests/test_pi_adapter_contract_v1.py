from dataclasses import replace
import hashlib

import pytest

from koschei.pi_adapter_contract_v1 import (
    PiAdapterContractError,
    admit_pi_external_evidence_v1,
    issue_pi_adapter_capability_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def cap(*, actions=("identity.verify", "payment.observe"), start=7, end=9):
    return issue_pi_adapter_capability_v1(
        app_id="koschei-lab-pi",
        subject_scope_digest=dhex("pi-subject-scope"),
        allowed_actions=actions,
        valid_from_epoch=start,
        expires_before_epoch=end,
    )


def test_pi_adapter_capability_is_non_authoritative_and_time_scoped():
    capability = cap()
    assert capability.authority is False
    assert capability.permits("identity.verify", current_epoch=7)
    assert capability.permits("payment.observe", current_epoch=8)
    assert not capability.permits("identity.verify", current_epoch=9)


def test_pi_adapter_capability_cannot_gain_unknown_action():
    with pytest.raises(PiAdapterContractError, match="unknown Pi adapter action"):
        cap(actions=("disk.read",))


def test_pi_adapter_capability_rejects_tampering():
    capability = cap()
    forged = replace(capability, allowed_actions=("payment.request",))
    with pytest.raises(PiAdapterContractError, match="seal mismatch"):
        forged.assert_sealed()


def test_pi_external_evidence_requires_live_explicit_action():
    capability = cap(actions=("payment.observe",))
    evidence = admit_pi_external_evidence_v1(
        capability,
        action="payment.observe",
        external_evidence_digest=dhex("settlement-observation"),
        observed_epoch=8,
    )
    assert evidence.authority is False
    evidence.assert_sealed(capability)


def test_pi_external_evidence_rejects_ungranted_action():
    capability = cap(actions=("identity.verify",))
    with pytest.raises(PiAdapterContractError, match="outside capability scope"):
        admit_pi_external_evidence_v1(
            capability,
            action="payment.request",
            external_evidence_digest=dhex("payment-intent"),
            observed_epoch=7,
        )


def test_pi_external_evidence_rejects_expired_capability():
    capability = cap(actions=("payment.observe",), start=7, end=8)
    with pytest.raises(PiAdapterContractError, match="outside capability scope"):
        admit_pi_external_evidence_v1(
            capability,
            action="payment.observe",
            external_evidence_digest=dhex("late-settlement"),
            observed_epoch=8,
        )


def test_pi_external_evidence_cannot_be_rebound_to_another_capability():
    first = cap(actions=("payment.observe",))
    second = issue_pi_adapter_capability_v1(
        app_id="other-pi-app",
        subject_scope_digest=dhex("other-subject"),
        allowed_actions=("payment.observe",),
        valid_from_epoch=7,
        expires_before_epoch=9,
    )
    evidence = admit_pi_external_evidence_v1(
        first,
        action="payment.observe",
        external_evidence_digest=dhex("settlement"),
        observed_epoch=7,
    )
    with pytest.raises(PiAdapterContractError, match="different capability"):
        evidence.assert_sealed(second)


def test_bool_is_not_accepted_as_epoch():
    capability = cap()
    with pytest.raises(PiAdapterContractError, match="current_epoch"):
        capability.permits("identity.verify", current_epoch=True)
