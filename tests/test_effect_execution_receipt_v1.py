from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import canonical_subject_scope_digest_v1, derive_canonical_authority_basis_v1
from koschei.effect_execution_receipt_v1 import EffectExecutionReceiptV1Error, execute_effect_with_receipt_v1
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
    dk, rk, ek = b"d" * 32, b"r" * 32, b"e" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, basis, mir=mir, request=request, proof=proof, bound=bound, decision_key=dk,
    )
    permit = mint_execution_permit_v1(grant, evidence, decision, runtime_key=rk, decision_key=dk)
    return locals()


def run(effect):
    items = chain()
    ledger = ExecutionPermitLedgerV1()
    consumption, receipt, result = execute_effect_with_receipt_v1(
        ledger=ledger, permit=items["permit"], runtime_key=items["rk"],
        decision_key=items["dk"], effect_key=items["ek"], grant=items["grant"],
        evidence=items["evidence"], decision=items["decision"], mir=items["mir"],
        request=items["request"], current_epoch=41, effect=effect,
    )
    items.update(ledger=ledger, consumption=consumption, receipt=receipt, result=result)
    return items


def test_runtime_measures_completed_bytes_and_authenticates_receipt():
    items = run(lambda req: b"subscription-enabled:" + req.digest.encode())
    assert items["receipt"].outcome == "effect-completed"
    assert items["result"] is not None
    items["receipt"].assert_authenticated(
        effect_key=items["ek"], consumption=items["consumption"], permit=items["permit"],
        mir=items["mir"], request=items["request"],
    )
    items["receipt"].assert_completed_result(items["result"])


def test_result_bytes_tamper_does_not_match_measurement():
    items = run(lambda _: b"ok")
    with pytest.raises(EffectExecutionReceiptV1Error, match="result bytes"):
        items["receipt"].assert_completed_result(b"tampered")


def test_callback_exception_becomes_authenticated_failed_receipt():
    def boom(_):
        raise RuntimeError("remote write rejected")
    items = run(boom)
    assert items["receipt"].outcome == "effect-failed"
    assert items["result"] is None
    items["receipt"].assert_authenticated(
        effect_key=items["ek"], consumption=items["consumption"], permit=items["permit"],
        mir=items["mir"], request=items["request"],
    )


def test_non_bytes_callback_result_is_fail_closed_as_failed_effect():
    items = run(lambda _: {"status": "ok"})
    assert items["receipt"].outcome == "effect-failed"
    assert items["result"] is None


def test_wrong_effect_key_rejects_receipt():
    items = run(lambda _: b"ok")
    with pytest.raises(EffectExecutionReceiptV1Error, match="authentication failed"):
        items["receipt"].assert_authenticated(
            effect_key=b"x" * 32, consumption=items["consumption"], permit=items["permit"],
            mir=items["mir"], request=items["request"],
        )


def test_receipt_outcome_or_measurement_tampering_rejects():
    items = run(lambda _: b"ok")
    for forged in (
        replace(items["receipt"], outcome="effect-failed"),
        replace(items["receipt"], measurement_digest=h("forged")),
    ):
        with pytest.raises(EffectExecutionReceiptV1Error, match="authentication failed"):
            forged.assert_authenticated(
                effect_key=items["ek"], consumption=items["consumption"], permit=items["permit"],
                mir=items["mir"], request=items["request"],
            )


def test_replay_is_rejected_before_callback_runs_again():
    items = chain()
    ledger = ExecutionPermitLedgerV1()
    calls = []
    kwargs = dict(
        ledger=ledger, permit=items["permit"], runtime_key=items["rk"],
        decision_key=items["dk"], effect_key=items["ek"], grant=items["grant"],
        evidence=items["evidence"], decision=items["decision"], mir=items["mir"],
        request=items["request"], current_epoch=41,
        effect=lambda _: calls.append(1) or b"ok",
    )
    execute_effect_with_receipt_v1(**kwargs)
    with pytest.raises(ExecutionPermitV1Error, match="replay detected"):
        execute_effect_with_receipt_v1(**kwargs)
    assert calls == [1]


def test_invalid_effect_key_fails_before_consumption_or_callback():
    items = chain()
    ledger = ExecutionPermitLedgerV1()
    calls = []
    with pytest.raises(EffectExecutionReceiptV1Error, match="effect_key"):
        execute_effect_with_receipt_v1(
            ledger=ledger, permit=items["permit"], runtime_key=items["rk"],
            decision_key=items["dk"], effect_key=b"short", grant=items["grant"],
            evidence=items["evidence"], decision=items["decision"], mir=items["mir"],
            request=items["request"], current_epoch=41,
            effect=lambda _: calls.append(1) or b"bad",
        )
    assert ledger.consumed == set()
    assert calls == []


def test_tampered_canonical_request_fails_before_consumption_or_callback():
    items = chain()
    ledger = ExecutionPermitLedgerV1()
    calls = []
    tampered = replace(items["request"], subject="treasury")
    with pytest.raises(ValueError):
        execute_effect_with_receipt_v1(
            ledger=ledger, permit=items["permit"], runtime_key=items["rk"],
            decision_key=items["dk"], effect_key=items["ek"], grant=items["grant"],
            evidence=items["evidence"], decision=items["decision"], mir=items["mir"],
            request=tampered, current_epoch=41,
            effect=lambda _: calls.append(1) or b"bad",
        )
    assert ledger.consumed == set()
    assert calls == []
