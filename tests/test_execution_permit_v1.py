from dataclasses import replace
import hashlib
import inspect

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import canonical_subject_scope_digest_v1, derive_canonical_authority_basis_v1
from koschei.execution_permit_v1 import ExecutionPermitLedgerV1, ExecutionPermitV1Error, mint_execution_permit_v1
from koschei.external_adapter_contract_v1 import admit_external_adapter_evidence_v1, issue_external_adapter_grant_v1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse

SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def dhex(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def fixture_bundle(*, fail_obligation=None):
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(
        activation_step_id=s.activation_step_id, obligation=s.obligation,
        subsystem=s.subsystem, proof_kind=s.proof_kind,
        evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),
        success=s.obligation != fail_obligation,
    ) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir, effect_id="pi-subscription-12", subject="withdrawal",
        operation="subscription.enable", request_digest=dhex("payload"),
        identity_digest=dhex("pi-user-12"), epoch=12, nonce_digest=dhex("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(mir=mir, request=request, proof=proof, bound=bound)
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",), valid_from_epoch=12, expires_before_epoch=13,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe", external_evidence_digest=dhex("settled-payment"), observed_epoch=12,
    )
    rk, dk = b"k" * 32, b"d" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, basis, mir=mir, request=request, proof=proof, bound=bound, decision_key=dk,
    )
    permit = None
    if decision.outcome == "allow":
        permit = mint_execution_permit_v1(grant, evidence, decision, runtime_key=rk, decision_key=dk)
    return grant, evidence, rk, dk, request, decision, permit


def auth(permit, rk, dk, grant, evidence, decision):
    permit.assert_authenticated(runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision)


def test_permit_inherits_exact_canonical_decision_scope():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    auth(permit, rk, dk, grant, evidence, decision)
    assert permit.authorization_decision_digest == decision.decision_digest
    assert permit.operation == request.operation
    assert permit.request_digest == request.digest
    assert permit.valid_epoch == request.epoch


def test_non_allow_native_decision_cannot_mint_permit():
    grant, evidence, rk, dk, _, decision, _ = fixture_bundle(fail_obligation="derive-least-authority")
    with pytest.raises(Exception, match="does not allow"):
        mint_execution_permit_v1(grant, evidence, decision, runtime_key=rk, decision_key=dk)


def test_minter_cannot_choose_operation_or_request():
    params = inspect.signature(mint_execution_permit_v1).parameters
    assert "operation" not in params and "request_digest" not in params


def test_tampered_operation_is_rejected():
    grant, evidence, rk, dk, _, decision, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="differs from authorization decision"):
        auth(replace(permit, operation="treasury.withdraw"), rk, dk, grant, evidence, decision)


def test_wrong_keys_reject_chain():
    grant, evidence, rk, dk, _, decision, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="authentication failed"):
        auth(permit, b"x" * 32, dk, grant, evidence, decision)
    with pytest.raises(Exception, match="authorization decision authentication failed"):
        auth(permit, rk, b"x" * 32, grant, evidence, decision)


def test_wrong_request_operation_and_epoch_are_not_live():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    common = dict(runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision)
    with pytest.raises(ExecutionPermitV1Error, match="not live"):
        ledger.consume(permit, **common, current_epoch=12, request_digest=dhex("other"), operation=request.operation)
    with pytest.raises(ExecutionPermitV1Error, match="not live"):
        ledger.consume(permit, **common, current_epoch=12, request_digest=request.digest, operation="treasury.withdraw")
    with pytest.raises(ExecutionPermitV1Error, match="not live"):
        ledger.consume(permit, **common, current_epoch=13, request_digest=request.digest, operation=request.operation)


def test_permit_is_single_use():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    ledger = ExecutionPermitLedgerV1()
    kwargs = dict(runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision,
                  current_epoch=12, request_digest=request.digest, operation=request.operation)
    ledger.consume(permit, **kwargs)
    with pytest.raises(ExecutionPermitV1Error, match="replay detected"):
        ledger.consume(permit, **kwargs)


def test_bool_epoch_and_short_key_fail_closed():
    grant, evidence, rk, dk, request, decision, permit = fixture_bundle()
    with pytest.raises(ExecutionPermitV1Error, match="current_epoch"):
        ExecutionPermitLedgerV1().consume(
            permit, runtime_key=rk, decision_key=dk, grant=grant, evidence=evidence, decision=decision,
            current_epoch=True, request_digest=request.digest, operation=request.operation,
        )
    with pytest.raises(ExecutionPermitV1Error, match="runtime_key.*at least 32 bytes"):
        mint_execution_permit_v1(grant, evidence, decision, runtime_key=b"short", decision_key=dk)
