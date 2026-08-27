from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import canonical_subject_scope_digest_v1, derive_canonical_authority_basis_v1
from koschei.effect_execution_receipt_v1 import (
    EffectExecutionReceiptV1Error,
    execute_effect_with_receipt_v1,
)
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


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def chain():
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(
        activation_step_id=s.activation_step_id, obligation=s.obligation,
        subsystem=s.subsystem, proof_kind=s.proof_kind,
        evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(), success=True,
    ) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir, effect_id="pi-subscription-41", subject="withdrawal",
        operation="subscription.enable", request_digest=h("payload"),
        identity_digest=h("pi-user-41"), epoch=41, nonce_digest=h("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(mir=mir, request=request, proof=proof, bound=bound)
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",), valid_from_epoch=41, expires_before_epoch=42,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe", external_evidence_digest=h("settled-payment"), observed_epoch=41,
    )
    decision_key, runtime_key, effect_key = b"d" * 32, b"r" * 32, b"e" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, basis, mir=mir, request=request, proof=proof, bound=bound,
        decision_key=decision_key,
    )
    permit = mint_execution_permit_v1(
        grant, evidence, decision, runtime_key=runtime_key, decision_key=decision_key,
    )
    return grant, evidence, request, decision, permit, decision_key, runtime_key, effect_key


def execute(effect):
    grant, evidence, request, decision, permit, dk, rk, ek = chain()
    ledger = ExecutionPermitLedgerV1()
    consumption, receipt, result = execute_effect_with_receipt_v1(
        ledger=ledger, permit=permit, runtime_key=rk, decision_key=dk, effect_key=ek,
        grant=grant, evidence=evidence, decision=decision, request=request,
        current_epoch=41, effect=effect,
    )
    return grant, evidence, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result


def test_runtime_measures_completed_bytes_and_authenticates_receipt():
    *_, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result = execute(
        lambda req: b"subscription-enabled:" + req.digest.encode()
    )
    assert receipt.outcome == "effect-completed"
    assert result is not None
    receipt.assert_authenticated(effect_key=ek, consumption=consumption, permit=permit, request=request)
    receipt.assert_completed_result(result)


def test_result_bytes_tamper_does_not_match_measurement():
    *_, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result = execute(lambda _: b"ok")
    with pytest.raises(EffectExecutionReceiptV1Error, match="result bytes"):
        receipt.assert_completed_result(b"tampered")


def test_callback_exception_becomes_authenticated_failed_receipt():
    def boom(_):
        raise RuntimeError("remote write rejected")
    *_, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result = execute(boom)
    assert receipt.outcome == "effect-failed"
    assert result is None
    receipt.assert_authenticated(effect_key=ek, consumption=consumption, permit=permit, request=request)
    with pytest.raises(EffectExecutionReceiptV1Error, match="does not describe completion"):
        receipt.assert_completed_result(b"anything")


def test_non_bytes_callback_result_is_fail_closed_as_failed_effect():
    *_, receipt, result = execute(lambda _: {"status": "ok"})[-2:]
    assert receipt.outcome == "effect-failed"
    assert result is None


def test_wrong_effect_key_rejects_receipt():
    *_, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result = execute(lambda _: b"ok")
    with pytest.raises(EffectExecutionReceiptV1Error, match="authentication failed"):
        receipt.assert_authenticated(effect_key=b"x" * 32, consumption=consumption, permit=permit, request=request)


def test_receipt_outcome_or_measurement_tampering_rejects():
    *_, request, decision, permit, dk, rk, ek, ledger, consumption, receipt, result = execute(lambda _: b"ok")
    with pytest.raises(EffectExecutionReceiptV1Error, match="authentication failed"):
        replace(receipt, outcome="effect-failed").assert_authenticated(
            effect_key=ek, consumption=consumption, permit=permit, request=request,
        )
    with pytest.raises(EffectExecutionReceiptV1Error, match="authentication failed"):
        replace(receipt, measurement_digest=h("forged")).assert_authenticated(
            effect_key=ek, consumption=consumption, permit=permit, request=request,
        )


def test_replay_is_rejected_before_callback_runs_again():
    grant, evidence, request, decision, permit, dk, rk, ek = chain()
    ledger = ExecutionPermitLedgerV1()
    calls = []
    kwargs = dict(
        ledger=ledger, permit=permit, runtime_key=rk, decision_key=dk, effect_key=ek,
        grant=grant, evidence=evidence, decision=decision, request=request, current_epoch=41,
        effect=lambda _: calls.append(1) or b"ok",
    )
    execute_effect_with_receipt_v1(**kwargs)
    with pytest.raises(ExecutionPermitV1Error, match="replay detected"):
        execute_effect_with_receipt_v1(**kwargs)
    assert calls == [1]


def test_wrong_request_is_rejected_before_consumption_or_effect():
    grant, evidence, request, decision, permit, dk, rk, ek = chain()
    other = replace(request, operation="treasury.withdraw")
    calls = []
    with pytest.raises(EffectExecutionReceiptV1Error, match="outside execution permit"):
        execute_effect_with_receipt_v1(
            ledger=ExecutionPermitLedgerV1(), permit=permit, runtime_key=rk,
            decision_key=dk, effect_key=ek, grant=grant, evidence=evidence,
            decision=decision, request=other, current_epoch=41,
            effect=lambda _: calls.append(1) or b"bad",
        )
    assert calls == []
