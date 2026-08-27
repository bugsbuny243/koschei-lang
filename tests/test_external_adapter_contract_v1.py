from dataclasses import replace
import hashlib

import pytest

from koschei.external_adapter_contract_v1 import (
    ExternalAdapterContractError,
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def grant(provider: str = "pi"):
    return issue_external_adapter_grant_v1(
        provider_id=provider,
        consumer_id="koschei-lab",
        subject_scope_digest=dhex("subject"),
        allowed_actions=("identity.verify", "payment.observe"),
        valid_from_epoch=4,
        expires_before_epoch=7,
    )


def test_external_grant_is_provider_consumer_subject_action_and_time_scoped():
    g = grant()
    g.assert_sealed()
    assert g.provider_id == "pi"
    assert g.consumer_id == "koschei-lab"
    assert g.permits("identity.verify", current_epoch=4)
    assert g.permits("payment.observe", current_epoch=6)
    assert not g.permits("payment.request", current_epoch=5)
    assert not g.permits("identity.verify", current_epoch=7)


def test_external_grant_rejects_tampering():
    g = grant()
    with pytest.raises(ExternalAdapterContractError, match="seal mismatch"):
        replace(g, consumer_id="attacker-app").assert_sealed()


def test_external_grant_rejects_bool_epoch():
    g = grant()
    with pytest.raises(ExternalAdapterContractError, match="non-negative integer"):
        g.permits("identity.verify", current_epoch=True)


def test_external_evidence_is_bound_to_exact_grant_and_provider():
    g = grant()
    e = admit_external_adapter_evidence_v1(
        g,
        action="identity.verify",
        external_evidence_digest=dhex("pi-proof"),
        observed_epoch=5,
    )
    e.assert_sealed(g)
    assert e.authority is False
    assert e.provider_id == "pi"

    other = grant(provider="bank")
    with pytest.raises(ExternalAdapterContractError, match="different grant|provider"):
        e.assert_sealed(other)


def test_external_evidence_cannot_escape_action_scope_or_lifetime():
    g = grant()
    with pytest.raises(ExternalAdapterContractError, match="outside grant scope or lifetime"):
        admit_external_adapter_evidence_v1(
            g,
            action="payment.request",
            external_evidence_digest=dhex("not-granted"),
            observed_epoch=5,
        )
    with pytest.raises(ExternalAdapterContractError, match="outside grant scope or lifetime"):
        admit_external_adapter_evidence_v1(
            g,
            action="identity.verify",
            external_evidence_digest=dhex("expired"),
            observed_epoch=7,
        )


def test_external_evidence_tampering_fails_closed():
    g = grant()
    e = admit_external_adapter_evidence_v1(
        g,
        action="identity.verify",
        external_evidence_digest=dhex("proof"),
        observed_epoch=5,
    )
    with pytest.raises(ExternalAdapterContractError, match="seal mismatch"):
        replace(e, external_evidence_digest=dhex("forged")).assert_sealed(g)
