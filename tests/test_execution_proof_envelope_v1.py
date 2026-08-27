from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.canonical_authority_basis_v1 import (
    canonical_subject_scope_digest_v1,
    derive_canonical_authority_basis_v1,
)
from koschei.execution_permit_v1 import ExecutionPermitLedgerV1, mint_execution_permit_v1
from koschei.execution_proof_envelope_v1 import (
    ExecutionProofEnvelopeV1Error,
    seal_execution_proof_envelope_v1,
)
from koschei.external_adapter_contract_v1 import (
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)
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


def h(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def bundle():
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=hashlib.sha256(step.binding_digest.encode()).hexdigest(),
            success=True,
        )
        for step in plan.steps
    ]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir,
        effect_id="pi-subscription-41",
        subject="withdrawal",
        operation="subscription.enable",
        request_digest=h("payload-41"),
        identity_digest=h("pi-user-41"),
        epoch=41,
        nonce_digest=h("nonce-41"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(
        mir=mir, request=request, proof=proof, bound=bound,
    )
    grant = issue_external_adapter_grant_v1(
        provider_id="pi",
        consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",),
        valid_from_epoch=41,
        expires_before_epoch=42,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant,
        action="payment.observe",
        external_evidence_digest=h("settled-payment-41"),
        observed_epoch=41,
    )
    decision_key = b"d" * 32
    runtime_key = b"r" * 32
    decision = issue_authorization_decision_v1(
        grant,
        evidence,
        basis,
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
        decision_key=decision_key,
    )
    permit = mint_execution_permit_v1(
        grant,
        evidence,
        decision,
        runtime_key=runtime_key,
        decision_key=decision_key,
    )
    ledger = ExecutionPermitLedgerV1()
    consumption = ledger.consume(
        permit,
        runtime_key=runtime_key,
        decision_key=decision_key,
        grant=grant,
        evidence=evidence,
        decision=decision,
        current_epoch=41,
        request_digest=request.digest,
        operation=request.operation,
    )
    return {
        "mir": mir,
        "proof": proof,
        "request": request,
        "bound": bound,
        "basis": basis,
        "grant": grant,
        "evidence": evidence,
        "decision": decision,
        "permit": permit,
        "consumption": consumption,
        "decision_key": decision_key,
        "runtime_key": runtime_key,
        "ledger": ledger,
    }


def seal(items):
    return seal_execution_proof_envelope_v1(
        grant=items["grant"],
        evidence=items["evidence"],
        mir=items["mir"],
        request=items["request"],
        proof=items["proof"],
        bound=items["bound"],
        basis=items["basis"],
        decision=items["decision"],
        permit=items["permit"],
        consumption=items["consumption"],
        decision_key=items["decision_key"],
        runtime_key=items["runtime_key"],
    )


def verify(envelope, items):
    envelope.assert_valid(
        grant=items["grant"],
        evidence=items["evidence"],
        mir=items["mir"],
        request=items["request"],
        proof=items["proof"],
        bound=items["bound"],
        basis=items["basis"],
        decision=items["decision"],
        permit=items["permit"],
        consumption=items["consumption"],
        decision_key=items["decision_key"],
        runtime_key=items["runtime_key"],
    )


def test_envelope_links_complete_chain_through_authenticated_consumption():
    items = bundle()
    envelope = seal(items)
    verify(envelope, items)
    assert envelope.grant_digest == items["grant"].grant_digest
    assert envelope.evidence_digest == items["evidence"].evidence_digest
    assert envelope.canonical_request_digest == items["request"].digest
    assert envelope.authority_basis_digest == items["basis"].basis_digest
    assert envelope.authorization_decision_digest == items["decision"].decision_digest
    assert envelope.permit_digest == items["permit"].permit_digest
    assert envelope.consumption_receipt_digest == items["consumption"].receipt_digest
    assert envelope.terminal_state == "permit-consumed"
    assert envelope.authority is False


def test_consumption_receipt_is_bound_to_exact_permit_scope():
    items = bundle()
    receipt = items["consumption"]
    receipt.assert_authenticated(runtime_key=items["runtime_key"], permit=items["permit"])
    with pytest.raises(ValueError, match="operation mismatch"):
        replace(receipt, operation="treasury.withdraw").assert_authenticated(
            runtime_key=items["runtime_key"], permit=items["permit"],
        )


def test_forged_consumption_receipt_cannot_enter_envelope():
    items = bundle()
    items["consumption"] = replace(items["consumption"], receipt_digest=h("forged-receipt"))
    with pytest.raises(ValueError, match="consumption receipt authentication failed"):
        seal(items)


def test_envelope_digest_tampering_is_rejected():
    items = bundle()
    envelope = seal(items)
    forged = replace(envelope, envelope_digest=h("forged-envelope"))
    with pytest.raises(ExecutionProofEnvelopeV1Error, match="seal mismatch"):
        verify(forged, items)


def test_envelope_cannot_relabel_terminal_state_as_effect_completed():
    items = bundle()
    envelope = seal(items)
    forged = replace(envelope, terminal_state="effect-completed")
    with pytest.raises(ExecutionProofEnvelopeV1Error, match="terminal state"):
        verify(forged, items)


def test_wrong_runtime_key_breaks_consumption_and_envelope_verification():
    items = bundle()
    envelope = seal(items)
    items["runtime_key"] = b"x" * 32
    with pytest.raises(ValueError, match="authentication failed"):
        verify(envelope, items)


def test_consumed_permit_still_cannot_be_consumed_twice():
    items = bundle()
    with pytest.raises(ValueError, match="replay detected"):
        items["ledger"].consume(
            items["permit"],
            runtime_key=items["runtime_key"],
            decision_key=items["decision_key"],
            grant=items["grant"],
            evidence=items["evidence"],
            decision=items["decision"],
            current_epoch=41,
            request_digest=items["request"].digest,
            operation=items["request"].operation,
        )
