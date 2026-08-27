from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import canonical_subject_scope_digest_v1, derive_canonical_authority_basis_v1
from koschei.effect_execution_proof_envelope_v1 import (
    EffectExecutionProofEnvelopeV1Error,
    seal_effect_execution_proof_envelope_v1,
)
from koschei.effect_execution_receipt_v1 import execute_effect_with_receipt_v1
from koschei.execution_permit_v1 import ExecutionPermitLedgerV1, mint_execution_permit_v1
from koschei.execution_proof_envelope_v1 import seal_execution_proof_envelope_v1
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


def chain(effect, *, nonce="nonce-51"):
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(
        activation_step_id=s.activation_step_id, obligation=s.obligation,
        subsystem=s.subsystem, proof_kind=s.proof_kind,
        evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(), success=True,
    ) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir, effect_id="effect-51", subject="withdrawal", operation="subscription.enable",
        request_digest=h("payload-51"), identity_digest=h("pi-user-51"), epoch=51,
        nonce_digest=h(nonce),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(mir=mir, request=request, proof=proof, bound=bound)
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",), valid_from_epoch=51, expires_before_epoch=52,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe", external_evidence_digest=h("settled-payment-51"), observed_epoch=51,
    )
    dk, rk, ek = b"d" * 32, b"r" * 32, b"e" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, basis, mir=mir, request=request, proof=proof, bound=bound,
        decision_key=dk,
    )
    permit = mint_execution_permit_v1(
        grant, evidence, decision, runtime_key=rk, decision_key=dk,
    )
    consumption, effect_receipt, result = execute_effect_with_receipt_v1(
        ledger=ExecutionPermitLedgerV1(), permit=permit, runtime_key=rk,
        decision_key=dk, effect_key=ek, grant=grant, evidence=evidence,
        decision=decision, mir=mir, request=request, current_epoch=51, effect=effect,
    )
    base = seal_execution_proof_envelope_v1(
        grant=grant, evidence=evidence, mir=mir, request=request, proof=proof,
        bound=bound, basis=basis, decision=decision, permit=permit,
        consumption=consumption, decision_key=dk, runtime_key=rk,
    )
    terminal = seal_effect_execution_proof_envelope_v1(
        base=base, effect_receipt=effect_receipt, grant=grant, evidence=evidence,
        mir=mir, request=request, proof=proof, bound=bound, basis=basis,
        decision=decision, permit=permit, consumption=consumption,
        decision_key=dk, runtime_key=rk, effect_key=ek,
    )
    return locals()


def validate(items, envelope=None):
    terminal = envelope or items["terminal"]
    terminal.assert_valid(
        base=items["base"], effect_receipt=items["effect_receipt"],
        grant=items["grant"], evidence=items["evidence"], mir=items["mir"],
        request=items["request"], proof=items["proof"], bound=items["bound"],
        basis=items["basis"], decision=items["decision"], permit=items["permit"],
        consumption=items["consumption"], decision_key=items["dk"],
        runtime_key=items["rk"], effect_key=items["ek"],
    )


def test_completed_effect_is_layered_over_permit_consumed_base():
    items = chain(lambda _: b"local-effect-complete")
    validate(items)
    assert items["base"].terminal_state == "permit-consumed"
    assert items["terminal"].terminal_state == "effect-completed"
    assert items["terminal"].authority is False


def test_failed_effect_gets_effect_failed_terminal():
    def fail(_):
        raise RuntimeError("remote dependency rejected")
    items = chain(fail)
    validate(items)
    assert items["terminal"].terminal_state == "effect-failed"
    assert items["result"] is None


def test_terminal_state_cannot_be_relabelled():
    items = chain(lambda _: b"ok")
    forged = replace(items["terminal"], terminal_state="effect-failed")
    with pytest.raises(EffectExecutionProofEnvelopeV1Error, match="terminal state mismatch"):
        validate(items, forged)


def test_measurement_or_effect_receipt_cannot_be_relabelled():
    items = chain(lambda _: b"ok")
    forged = replace(items["terminal"], measurement_digest=h("fake-measurement"))
    with pytest.raises(EffectExecutionProofEnvelopeV1Error, match="measurement mismatch"):
        validate(items, forged)


def test_effect_receipt_cannot_move_to_another_canonical_request_chain():
    first = chain(lambda _: b"first", nonce="nonce-a")
    second = chain(lambda _: b"second", nonce="nonce-b")
    assert first["request"].digest != second["request"].digest
    forged = replace(first["terminal"], base_execution_envelope_digest=second["base"].envelope_digest)
    with pytest.raises((EffectExecutionProofEnvelopeV1Error, ValueError)):
        forged.assert_valid(
            base=second["base"], effect_receipt=first["effect_receipt"],
            grant=second["grant"], evidence=second["evidence"], mir=second["mir"],
            request=second["request"], proof=second["proof"], bound=second["bound"],
            basis=second["basis"], decision=second["decision"], permit=second["permit"],
            consumption=second["consumption"], decision_key=second["dk"],
            runtime_key=second["rk"], effect_key=first["ek"],
        )
