from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import (
    AuthorizationDecisionV1Error,
    issue_authorization_decision_v1,
)
from koschei.external_adapter_contract_v1 import (
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def bundle(*, outcome="allow"):
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=dhex("subject"), allowed_actions=("payment.observe",),
        valid_from_epoch=21, expires_before_epoch=22,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe",
        external_evidence_digest=dhex("settled-payment"), observed_epoch=21,
    )
    key = b"d" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, decision_key=key, operation="subscription.enable",
        request_digest=dhex("request"), authority_basis_digest=dhex("capability-basis"),
        policy_digest=dhex("subscription-policy-v1"), outcome=outcome,
    )
    return grant, evidence, key, decision


def test_allow_decision_is_bound_to_authority_policy_request_and_evidence():
    grant, evidence, key, decision = bundle()
    decision.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)
    decision.assert_allows()
    assert decision.authority_basis_digest == dhex("capability-basis")
    assert decision.policy_digest == dhex("subscription-policy-v1")
    assert decision.decision_epoch == 21


def test_deny_decision_cannot_be_used_as_allow():
    _, _, _, decision = bundle(outcome="deny")
    with pytest.raises(AuthorizationDecisionV1Error, match="does not allow"):
        decision.assert_allows()


def test_contain_decision_cannot_be_used_as_allow():
    _, _, _, decision = bundle(outcome="contain")
    with pytest.raises(AuthorizationDecisionV1Error, match="does not allow"):
        decision.assert_allows()


def test_operation_tampering_breaks_authentication():
    grant, evidence, key, decision = bundle()
    forged = replace(decision, operation="treasury.withdraw")
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        forged.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)


def test_authority_basis_tampering_breaks_authentication():
    grant, evidence, key, decision = bundle()
    forged = replace(decision, authority_basis_digest=dhex("forged-authority"))
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        forged.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)


def test_policy_tampering_breaks_authentication():
    grant, evidence, key, decision = bundle()
    forged = replace(decision, policy_digest=dhex("other-policy"))
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        forged.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)


def test_wrong_decision_key_rejects():
    grant, evidence, _, decision = bundle()
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        decision.assert_authenticated(decision_key=b"x" * 32, grant=grant, evidence=evidence)


def test_decision_cannot_be_rebound_to_other_evidence():
    grant, _, key, decision = bundle()
    other = admit_external_adapter_evidence_v1(
        grant, action="payment.observe", external_evidence_digest=dhex("other-payment"), observed_epoch=21,
    )
    with pytest.raises(AuthorizationDecisionV1Error, match="different evidence"):
        decision.assert_authenticated(decision_key=key, grant=grant, evidence=other)
