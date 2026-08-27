from dataclasses import replace
import hashlib

import pytest

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


def fixture_bundle():
    grant = issue_external_adapter_grant_v1(
        provider_id="pi",
        consumer_id="koschei-lab-pi",
        subject_scope_digest=dhex("subject"),
        allowed_actions=("payment.observe",),
        valid_from_epoch=12,
        expires_before_epoch=13,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant,
        action="payment.observe",
        external_evidence_digest=dhex("settled-payment"),
        observed_epoch=12,
    )
    key = b"k" * 32
    request = dhex("unlock-premium-build-request")
    permit = mint_execution_permit_v1(
        grant,
        evidence,
        runtime_key=key,
        operation="subscription.enable",
        request_digest=request,
    )
    return grant, evidence, key, request, permit


def test_permit_is_bound_to_evidence_subject_operation_request_and_epoch():
    grant, evidence, key, request, permit = fixture_bundle()
    permit.assert_authenticated(runtime_key=key, grant=grant, evidence=evidence)
    assert permit.provider_id == "pi"
    assert permit.consumer_id == "koschei-lab-pi"
    assert permit.subject_scope_digest == grant.subject_scope_digest
    assert permit.operation == "subscription.enable"
    assert permit.request_digest == request
    assert permit.valid_epoch == 12
    assert permit.single_use is True


def test_tampered_operation_cannot_be_resealed_without_runtime_key():
    grant, evidence, key, _, permit = fixture_bundle()
    forged = replace(permit, operation="treasury.withdraw")
    with pytest.raises(ExecutionPermitV1Error, match="authentication failed"):
        forged.assert_authenticated(runtime_key=key, grant=grant, evidence=evidence)


def test_wrong_runtime_key_rejects_permit():
    grant, evidence, _, _, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="authentication failed"):
        permit.assert_authenticated(runtime_key=b"x" * 32, grant=grant, evidence=evidence)


def test_permit_cannot_be_rebound_to_other_evidence():
    grant, evidence, key, _, permit = fixture_bundle()
    other = admit_external_adapter_evidence_v1(
        grant,
        action="payment.observe",
        external_evidence_digest=dhex("another-payment"),
        observed_epoch=12,
    )
    with pytest.raises(ExecutionPermitV1Error, match="different external evidence"):
        permit.assert_authenticated(runtime_key=key, grant=grant, evidence=other)


def test_permit_rejects_wrong_request_even_in_same_epoch():
    grant, evidence, key, _, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(
            permit,
            runtime_key=key,
            grant=grant,
            evidence=evidence,
            current_epoch=12,
            request_digest=dhex("different-request"),
            operation="subscription.enable",
        )


def test_permit_rejects_wrong_operation_even_in_same_epoch():
    grant, evidence, key, request, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(
            permit,
            runtime_key=key,
            grant=grant,
            evidence=evidence,
            current_epoch=12,
            request_digest=request,
            operation="treasury.withdraw",
        )


def test_permit_expires_when_epoch_rotates():
    grant, evidence, key, request, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="not live for this request"):
        ledger.consume(
            permit,
            runtime_key=key,
            grant=grant,
            evidence=evidence,
            current_epoch=13,
            request_digest=request,
            operation="subscription.enable",
        )


def test_permit_is_single_use_and_replay_is_rejected():
    grant, evidence, key, request, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    ledger.consume(
        permit,
        runtime_key=key,
        grant=grant,
        evidence=evidence,
        current_epoch=12,
        request_digest=request,
        operation="subscription.enable",
    )
    with pytest.raises(ExecutionPermitV1Error, match="replay detected"):
        ledger.consume(
            permit,
            runtime_key=key,
            grant=grant,
            evidence=evidence,
            current_epoch=12,
            request_digest=request,
            operation="subscription.enable",
        )


def test_bool_epoch_is_rejected():
    grant, evidence, key, request, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    with pytest.raises(ExecutionPermitV1Error, match="current_epoch"):
        ledger.consume(
            permit,
            runtime_key=key,
            grant=grant,
            evidence=evidence,
            current_epoch=True,
            request_digest=request,
            operation="subscription.enable",
        )


def test_short_runtime_key_is_rejected():
    grant, evidence, _, request, _ = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="at least 32 bytes"):
        mint_execution_permit_v1(
            grant,
            evidence,
            runtime_key=b"short",
            operation="subscription.enable",
            request_digest=request,
        )
