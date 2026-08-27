from dataclasses import replace
import hashlib
import inspect

import pytest

from koschei.authorization_decision_v1 import (
    AuthorizationDecisionV1Error,
    issue_authorization_decision_v1,
)
from koschei.canonical_authority_basis_v1 import (
    canonical_subject_scope_digest_v1,
    derive_canonical_authority_basis_v1,
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


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _proof(mir, *, fail_obligation=None):
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=hashlib.sha256(step.binding_digest.encode()).hexdigest(),
            success=step.obligation != fail_obligation,
        )
        for step in plan.steps
    ]
    return seal_native_sigil_proof(mir, receipts)


def bundle(*, fail_obligation=None, epoch=21):
    mir = lower_native_sigils(parse(SOURCE))
    proof = _proof(mir, fail_obligation=fail_obligation)
    request = seal_effect_request(
        mir,
        effect_id="pi-subscription-21",
        subject="withdrawal",
        operation="subscription.enable",
        request_digest=dhex("request"),
        identity_digest=dhex("pi-user-21"),
        epoch=epoch,
        nonce_digest=dhex("nonce-21"),
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
        valid_from_epoch=epoch,
        expires_before_epoch=epoch + 1,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant,
        action="payment.observe",
        external_evidence_digest=dhex("settled-payment"),
        observed_epoch=epoch,
    )
    key = b"d" * 32
    decision = issue_authorization_decision_v1(
        grant, evidence, basis,
        mir=mir, request=request, proof=proof, bound=bound, decision_key=key,
    )
    return mir, proof, request, bound, basis, grant, evidence, key, decision


def test_decision_is_derived_from_native_authority_basis():
    mir, _, request, _, basis, grant, evidence, key, decision = bundle()
    decision.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)
    decision.assert_allows()
    assert decision.authority_basis_digest == basis.basis_digest
    assert decision.policy_digest == mir.fingerprint
    assert decision.operation == request.operation
    assert decision.request_digest == request.digest
    assert decision.decision_epoch == request.epoch


def test_public_issuer_has_no_authority_digest_or_outcome_injection_parameters():
    parameters = inspect.signature(issue_authorization_decision_v1).parameters
    for forbidden in ("authority_basis_digest", "policy_digest", "outcome", "operation", "request_digest"):
        assert forbidden not in parameters


def test_deny_native_enforcement_cannot_be_used_as_allow():
    *_, decision = bundle(fail_obligation="derive-least-authority")
    assert decision.outcome == "deny"
    with pytest.raises(AuthorizationDecisionV1Error, match="does not allow"):
        decision.assert_allows()


def test_contain_native_enforcement_cannot_be_used_as_allow():
    *_, decision = bundle(fail_obligation="fence-stale-writers")
    assert decision.outcome == "contain"
    with pytest.raises(AuthorizationDecisionV1Error, match="does not allow"):
        decision.assert_allows()


def test_operation_tampering_breaks_decision_authentication():
    *_, grant, evidence, key, decision = bundle()
    forged = replace(decision, operation="treasury.withdraw")
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        forged.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)


def test_authority_basis_tampering_breaks_decision_authentication():
    *_, grant, evidence, key, decision = bundle()
    forged = replace(decision, authority_basis_digest=dhex("forged-authority"))
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        forged.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)


def test_tampered_native_basis_is_rejected_before_decision_issuance():
    mir, proof, request, bound, basis, grant, evidence, key, _ = bundle()
    forged_basis = replace(basis, operation="treasury.withdraw")
    with pytest.raises(ValueError, match="authority-basis operation mismatch"):
        issue_authorization_decision_v1(
            grant, evidence, forged_basis,
            mir=mir, request=request, proof=proof, bound=bound, decision_key=key,
        )


def test_external_subject_scope_must_match_canonical_request_identity():
    mir, proof, request, bound, basis, _, _, key, _ = bundle()
    wrong_grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=dhex("wrong-subject"),
        allowed_actions=("payment.observe",), valid_from_epoch=21, expires_before_epoch=22,
    )
    evidence = admit_external_adapter_evidence_v1(
        wrong_grant, action="payment.observe",
        external_evidence_digest=dhex("settled-payment"), observed_epoch=21,
    )
    with pytest.raises(AuthorizationDecisionV1Error, match="subject scope"):
        issue_authorization_decision_v1(
            wrong_grant, evidence, basis,
            mir=mir, request=request, proof=proof, bound=bound, decision_key=key,
        )


def test_external_evidence_epoch_must_match_canonical_request_epoch():
    mir, proof, request, bound, basis, _, _, key, _ = bundle()
    grant = issue_external_adapter_grant_v1(
        provider_id="pi", consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",), valid_from_epoch=20, expires_before_epoch=22,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant, action="payment.observe",
        external_evidence_digest=dhex("settled-payment"), observed_epoch=20,
    )
    with pytest.raises(AuthorizationDecisionV1Error, match="authority epoch"):
        issue_authorization_decision_v1(
            grant, evidence, basis,
            mir=mir, request=request, proof=proof, bound=bound, decision_key=key,
        )


def test_wrong_decision_key_rejects():
    *_, grant, evidence, _, decision = bundle()
    with pytest.raises(AuthorizationDecisionV1Error, match="authentication failed"):
        decision.assert_authenticated(decision_key=b"x" * 32, grant=grant, evidence=evidence)
