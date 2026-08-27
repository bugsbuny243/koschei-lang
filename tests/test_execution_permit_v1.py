from dataclasses import replace
import hashlib
import inspect

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.execution_permit_v1 import (
    ExecutionPermitLedgerV1,
    ExecutionPermitV1Error,
    mint_execution_permit_v1,
)
from koschei.external_adapter_contract_v1 import (
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def fixture_bundle(*, outcome="allow"):
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=dhex("subject"), allowed_actions=("payment.observe",),
        valid_from_epoch=12, expires_before_epoch=13,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe",
        external_evidence_digest=dhex("settled-payment"), observed_epoch=12,
    )
    runtime_key = b"k" * 32
    decision_key = b"d" * 32
    request = dhex("unlock-premium-build-request")
    decision = issue_authorization_decision_v1(
        grant, evidence, decision_key=decision_key,
        operation="subscription.enable", request_digest=request,
        authority_basis_digest=dhex("subscription-capability"),
        policy_digest=dhex("subscription-policy-v1"), outcome=outcome,
    )
    permit = None
    if outcome == "allow":
        permit = mint_execution_permit_v1(
            grant, evidence, decision, runtime_key=runtime_key, decision_key=decision_key,
        )
    return grant, evidence, runtime_key, decision_key, request, decision, permit


def auth(permit, *, runtime_key, decision_key, grant, evidence, decision):
    permit.assert_authenticated(
        runtime_key=runtime_key, decision_key=decision_key,
        grant=grant, evidence=evidence, decision=decision,
    )


def test_permit_inherits_exact_authenticated_decision_scope():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    auth(permit, runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision)
    assert permit.authorization_decision_digest == decision.decision_digest
    assert permit.operation == "subscription.enable"
    assert permit.request_digest == request
    assert permit.valid_epoch == 12
    assert permit.single_use is True


def test_deny_decision_cannot_mint_permit():
    grant, evidence, rk, dk, _, decision, _ = fixture_bundle(outcome="deny")
    with pytest.raises(Exception, match="does not allow"):
        mint_execution_permit_v1(grant, evidence, decision, runtime_key=rk, decision_key=dk)


def test_minter_api_cannot_choose_operation_or_request_outside_decision():
    params = inspect.signature(mint_execution_permit_v1).parameters
    assert "operation" not in params
    assert "request_digest" not in params
    _, _, _, _, _, decision, permit = fixture_bundle()
    assert decision.operation == permit.operation == "subscription.enable"
    assert decision.request_digest == permit.request_digest


def test_tampered_operation_is_rejected_against_decision_before_mac_acceptance():
    grant, evidence, rk, dk, _, decision, permit = fixture_bundle()
    forged = replace(permit, operation="treasury.withdraw")
    with pytest.raises(ExecutionPermitV1Error, match="differs from authorization decision"):
        auth(forged, runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision)


def test_wrong_runtime_key_rejects_permit():
    grant, evidence, _, dk, _, decision, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="authentication failed"):
        auth(permit, runtime_key=b"x" * 32, decision_key=dk, grant=grant, evidence=evidence, decision=decision)


def test_wrong_decision_key_rejects_chain():
    grant, evidence, rk, _, _, decision, permit = fixture_bundle()
    with pytest.raises(Exception, match="authorization decision authentication failed"):
        auth(permit, runtime_key=rk, decision_key=b"x" * 32, grant=grant, evidence=evidence, decision=decision)


def test_permit_cannot_be_rebound_to_different_allow_decision():
    grant, evidence, rk, dk, _, _, permit = fixture_bundle()
    other = issue_authorization_decision_v1(
        grant, evidence, decision_key=dk, operation="subscription.disable",
        request_digest=dhex("other-request"), authority_basis_digest=dhex("subscription-capability"),
        policy_digest=dhex("subscription-policy-v1"), outcome="allow",
    )
    with pytest.raises(ExecutionPermitV1Error, match="different authorization decision"):
        auth(permit, runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=other)


def test_permit_rejects_wrong_request_same_epoch():
    grant, evidence, rk, dk, _, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(permit, runtime_key=rk, decision_key=dk, grant=grant,
                       evidence=evidence, decision=decision, current_epoch=12,
                       request_digest=dhex("different-request"), operation="subscription.enable")


def test_permit_rejects_wrong_operation_same_epoch():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(permit, runtime_key=rk, decision_key=dk, grant=grant,
                       evidence=evidence, decision=decision, current_epoch=12,
                       request_digest=request, operation="treasury.withdraw")


def test_permit_expires_when_epoch_rotates():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(permit, runtime_key=rk, decision_key=dk, grant=grant,
                       evidence=evidence, decision=decision, current_epoch=13,
                       request_digest=request, operation="subscription.enable")


def test_permit_is_single_use():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    kwargs = dict(runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence,
                  decision=decision, current_epoch=12, request_digest=request,
                  operation="subscription.enable")
    ledger.consume(permit, **kwargs)
    with pytest.raises(ExecutionPermitV1Error, match="replay detected"):
        ledger.consume(permit, **kwargs)


def test_bool_epoch_is_rejected():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="current_epoch"):
        ExecutionPermitLedgerV1().consume(
            permit, runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence,
            decision=decision, current_epoch=True, request_digest=request,
            operation="subscription.enable",
        )


def test_short_runtime_key_is_rejected():
    grant, evidence, _, dk, _, decision, _ = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="runtime_key.*at least 32 bytes"):
        mint_execution_permit_v1(grant, evidence, decision,
                                 runtime_key=b"short", decision_key=dk)
