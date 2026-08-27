from dataclasses import replace
import hashlib

import pytest

from koschei.canonical_authority_basis_v1 import (
    CanonicalAuthorityBasisV1Error,
    canonical_subject_scope_digest_v1,
    derive_canonical_authority_basis_v1,
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


def bundle(*, fail=None, epoch=9, nonce="n1"):
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [make_receipt(
        activation_step_id=s.activation_step_id, obligation=s.obligation,
        subsystem=s.subsystem, proof_kind=s.proof_kind,
        evidence_digest=hashlib.sha256(s.binding_digest.encode()).hexdigest(),
        success=s.obligation != fail,
    ) for s in plan.steps]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir, effect_id="effect-9", subject="withdrawal", operation="subscription.enable",
        request_digest=h("payload"), identity_digest=h("pi-user"), epoch=epoch,
        nonce_digest=h(nonce),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(mir=mir, request=request, proof=proof, bound=bound)
    return mir, proof, request, bound, basis


def test_basis_is_exact_receipt_of_existing_native_enforcement_chain():
    mir, proof, request, bound, basis = bundle()
    decision = basis.assert_sealed(mir=mir, request=request, proof=proof, bound=bound)
    assert decision.decision == "ALLOW"
    assert basis.canonical_request_digest == request.digest
    assert basis.request_bound_proof_digest == bound.digest
    assert basis.proof_digest == proof.digest
    assert basis.native_mir_fingerprint == mir.fingerprint
    assert basis.subject_scope_digest == canonical_subject_scope_digest_v1(request)
    assert basis.authority is False


def test_basis_preserves_native_deny_and_contain_outcomes():
    *_, deny = bundle(fail="derive-least-authority")
    *_, contain = bundle(fail="fence-stale-writers")
    assert deny.outcome == "DENY"
    assert contain.outcome == "CONTAIN"


def test_basis_operation_tamper_is_rejected():
    mir, proof, request, bound, basis = bundle()
    with pytest.raises(CanonicalAuthorityBasisV1Error, match="operation mismatch"):
        replace(basis, operation="treasury.withdraw").assert_sealed(
            mir=mir, request=request, proof=proof, bound=bound,
        )


def test_basis_cannot_follow_a_different_request_epoch_or_nonce():
    mir, proof, request, bound, basis = bundle()
    other = seal_effect_request(
        mir, effect_id="effect-9", subject="withdrawal", operation="subscription.enable",
        request_digest=h("payload"), identity_digest=h("pi-user"), epoch=10,
        nonce_digest=h("n2"),
    )
    with pytest.raises(ValueError):
        basis.assert_sealed(mir=mir, request=other, proof=proof, bound=bound)


def test_basis_digest_tamper_is_rejected():
    mir, proof, request, bound, basis = bundle()
    with pytest.raises(CanonicalAuthorityBasisV1Error, match="seal mismatch"):
        replace(basis, basis_digest=h("forged")).assert_sealed(
            mir=mir, request=request, proof=proof, bound=bound,
        )
