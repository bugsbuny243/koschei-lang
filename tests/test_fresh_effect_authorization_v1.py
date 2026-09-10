from dataclasses import replace
import hashlib

import pytest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.authorization_state_ledger_v1 import AuthorizationStateLedgerV1
from koschei.authorization_transition_v1 import (
    AuthorizationTransitionV1Error,
    ConstraintSetV1,
    DelegationLinkV1,
    IntentCommitmentV1,
    issue_authorization_state_v1,
    transition_authorization_state_v1,
)
from koschei.canonical_authority_basis_v1 import (
    canonical_subject_scope_digest_v1,
    derive_canonical_authority_basis_v1,
)
from koschei.execution_permit_v1 import ExecutionPermitLedgerV1, mint_execution_permit_v1
from koschei.external_adapter_contract_v1 import (
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)
from koschei.fresh_effect_authorization_v1 import (
    FreshEffectAuthorizationV1Error,
    canonical_execution_principal_v1,
    execute_effect_with_fresh_authorization_v1,
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


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def effect_chain():
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
        request_digest=h("payload"),
        identity_digest=h("pi-user-41"),
        epoch=41,
        nonce_digest=h("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
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
        external_evidence_digest=h("settled-payment"),
        observed_epoch=41,
    )
    dk, rk, ek = b"d" * 32, b"r" * 32, b"e" * 32
    decision = issue_authorization_decision_v1(
        grant,
        evidence,
        basis,
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
        decision_key=dk,
    )
    permit = mint_execution_permit_v1(
        grant,
        evidence,
        decision,
        runtime_key=rk,
        decision_key=dk,
    )
    return locals()


def exact_constraints(items, *, resource=None):
    request = items["request"]
    grant = items["grant"]
    return ConstraintSetV1(
        resources=(resource or request.subject,),
        operations=(request.operation,),
        arguments=(request.request_digest,),
        audience=(grant.consumer_id,),
        magnitude_max=None,
        valid_from_epoch=41,
        expires_before_epoch=42,
        delegation_depth=0,
        redelegation=False,
    )


def authority(items, *, resource=None):
    request = items["request"]
    principal = canonical_execution_principal_v1(request)
    intent = IntentCommitmentV1(
        principal=principal,
        intent_digest=request.digest,
        purpose_digest=h("enable-paid-subscription"),
        created_epoch=41,
    )
    link = DelegationLinkV1(
        delegation_id="effect-root",
        parent_delegation_id=None,
        issuer="human-owner",
        subject=principal,
        constraints=exact_constraints(items, resource=resource),
        parent_commitment=None,
        checked_epoch=41,
        signature_valid=True,
        revocation_status="valid",
    )
    delegation_chain = (link,)
    state = issue_authorization_state_v1(intent, delegation_chain, epoch=41)
    authorization_ledger = AuthorizationStateLedgerV1()
    authorization_ledger.register_initial(state)
    return intent, delegation_chain, state, authorization_ledger


def hardened_kwargs(items, *, authorization=None, effect=None):
    intent, delegation_chain, state, authorization_ledger = authorization or authority(items)
    permit_ledger = ExecutionPermitLedgerV1()
    calls = []
    callback = effect or (lambda _: calls.append(1) or b"ok")
    kwargs = dict(
        authorization_ledger=authorization_ledger,
        state=state,
        delegation_chain=delegation_chain,
        intent=intent,
        ledger=permit_ledger,
        permit=items["permit"],
        runtime_key=items["rk"],
        decision_key=items["dk"],
        effect_key=items["ek"],
        grant=items["grant"],
        evidence=items["evidence"],
        decision=items["decision"],
        mir=items["mir"],
        request=items["request"],
        current_epoch=41,
        effect=callback,
    )
    return kwargs, permit_ledger, calls


def test_fresh_current_authority_executes_exact_effect_once():
    items = effect_chain()
    kwargs, permit_ledger, calls = hardened_kwargs(items)
    snapshot, consumption, receipt, result = execute_effect_with_fresh_authorization_v1(**kwargs)

    assert snapshot.authority is False
    assert snapshot.execution_epoch == 41
    assert snapshot.intent_commitment_digest == kwargs["intent"].digest
    assert consumption.permit_digest == items["permit"].permit_digest
    assert receipt.outcome == "effect-completed"
    assert result == b"ok"
    assert calls == [1]
    assert items["permit"].permit_digest in permit_ledger.consumed


def test_advanced_revocation_head_rejects_old_state_before_effect_or_consumption():
    items = effect_chain()
    intent, delegation_chain, state, authorization_ledger = authority(items)
    revoked, transition = transition_authorization_state_v1(
        state,
        kind="REVOKE",
        epoch=42,
        reason_digest=h("owner-revoked"),
    )
    authorization_ledger.commit_transition(state, revoked, transition)
    kwargs, permit_ledger, calls = hardened_kwargs(
        items,
        authorization=(intent, delegation_chain, state, authorization_ledger),
    )

    with pytest.raises(AuthorizationTransitionV1Error, match="current monotonic head"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_unknown_revocation_status_fails_closed_before_effect_or_consumption():
    items = effect_chain()
    intent, delegation_chain, state, authorization_ledger = authority(items)
    unknown_chain = (replace(delegation_chain[0], revocation_status="unknown"),)
    kwargs, permit_ledger, calls = hardened_kwargs(
        items,
        authorization=(intent, unknown_chain, state, authorization_ledger),
    )

    with pytest.raises(AuthorizationTransitionV1Error, match="not currently valid"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_stale_delegation_check_fails_before_effect_or_consumption():
    items = effect_chain()
    intent, delegation_chain, state, authorization_ledger = authority(items)
    stale_chain = (replace(delegation_chain[0], checked_epoch=40),)
    kwargs, permit_ledger, calls = hardened_kwargs(
        items,
        authorization=(intent, stale_chain, state, authorization_ledger),
    )

    with pytest.raises(AuthorizationTransitionV1Error, match="stale for execution epoch"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_unavailable_authorization_head_fails_closed_before_effect_or_consumption():
    items = effect_chain()
    intent, delegation_chain, state, _ = authority(items)
    empty_ledger = AuthorizationStateLedgerV1()
    kwargs, permit_ledger, calls = hardened_kwargs(
        items,
        authorization=(intent, delegation_chain, state, empty_ledger),
    )

    with pytest.raises(AuthorizationTransitionV1Error, match="head is unavailable"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_effective_scope_must_be_exact_for_request():
    items = effect_chain()
    bad_authority = authority(items, resource="other-resource")
    kwargs, permit_ledger, calls = hardened_kwargs(items, authorization=bad_authority)

    with pytest.raises(FreshEffectAuthorizationV1Error, match="resource scope is not exact"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_intent_must_bind_exact_canonical_request():
    items = effect_chain()
    intent, delegation_chain, state, authorization_ledger = authority(items)
    forged_intent = replace(intent, intent_digest=h("different-request"))
    kwargs, permit_ledger, calls = hardened_kwargs(
        items,
        authorization=(forged_intent, delegation_chain, state, authorization_ledger),
    )

    with pytest.raises(FreshEffectAuthorizationV1Error, match="exact canonical request"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []


def test_request_epoch_mismatch_fails_before_effect_or_consumption():
    items = effect_chain()
    kwargs, permit_ledger, calls = hardened_kwargs(items)
    kwargs["current_epoch"] = 42

    with pytest.raises(FreshEffectAuthorizationV1Error, match="execution epoch"):
        execute_effect_with_fresh_authorization_v1(**kwargs)
    assert permit_ledger.consumed == set()
    assert calls == []
