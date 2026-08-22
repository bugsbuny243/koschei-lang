import hashlib
from dataclasses import replace

import pytest

from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import (
    NativeSigilRequestBindingError,
    bind_proof_to_request,
    enforce_bound_effect,
    seal_effect_request,
)
from koschei.parser import parse


SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def _mir():
    return lower_native_sigils(parse(SOURCE))


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


def _request(mir, *, payload="payload-a", nonce="nonce-a", epoch=7):
    return seal_effect_request(
        mir,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=hashlib.sha256(payload.encode()).hexdigest(),
        identity_digest=hashlib.sha256(b"operator-7").hexdigest(),
        epoch=epoch,
        nonce_digest=hashlib.sha256(nonce.encode()).hexdigest(),
    )


def test_allow_executes_only_for_exact_bound_request():
    mir = _mir()
    proof = _proof(mir)
    request = _request(mir)
    bound = bind_proof_to_request(mir, request, proof)
    calls = []

    decision, value = enforce_bound_effect(
        mir, request, proof, bound, lambda item: calls.append(item.digest) or "signed"
    )

    assert decision.decision == "ALLOW"
    assert value == "signed"
    assert calls == [request.digest]


def test_same_proof_cannot_be_replayed_for_different_payload():
    mir = _mir()
    proof = _proof(mir)
    request_a = _request(mir, payload="payload-a")
    bound = bind_proof_to_request(mir, request_a, proof)
    request_b = _request(mir, payload="payload-b")

    with pytest.raises(NativeSigilRequestBindingError, match="request mismatch"):
        enforce_bound_effect(mir, request_b, proof, bound, lambda _: "must-not-run")


def test_same_proof_cannot_be_replayed_across_epoch_or_nonce():
    mir = _mir()
    proof = _proof(mir)
    request = _request(mir, epoch=7, nonce="nonce-a")
    bound = bind_proof_to_request(mir, request, proof)

    with pytest.raises(NativeSigilRequestBindingError):
        bound.assert_sealed(mir, _request(mir, epoch=8, nonce="nonce-a"), proof)
    with pytest.raises(NativeSigilRequestBindingError):
        bound.assert_sealed(mir, _request(mir, epoch=7, nonce="nonce-b"), proof)


def test_privileged_subject_must_be_declared_by_vor():
    mir = _mir()
    with pytest.raises(NativeSigilRequestBindingError, match="vor binding"):
        seal_effect_request(
            mir,
            effect_id="x",
            subject="treasury",
            operation="signer.execute",
            request_digest="a",
            identity_digest="b",
            epoch=1,
            nonce_digest="c",
        )


def test_bound_proof_tampering_is_rejected():
    mir = _mir()
    proof = _proof(mir)
    request = _request(mir)
    bound = bind_proof_to_request(mir, request, proof)
    tampered = replace(bound, request_digest="0" * 64)

    with pytest.raises(NativeSigilRequestBindingError):
        tampered.assert_sealed(mir, request, proof)


def test_deny_and_contain_still_never_execute_effect():
    mir = _mir()
    for failed, expected in (
        ("derive-least-authority", "DENY"),
        ("fence-stale-writers", "CONTAIN"),
    ):
        proof = _proof(mir, fail_obligation=failed)
        request = _request(mir, nonce=failed)
        bound = bind_proof_to_request(mir, request, proof)
        calls = []
        decision, value = enforce_bound_effect(
            mir, request, proof, bound, lambda _: calls.append(1)
        )
        assert decision.decision == expected
        assert value is None
        assert calls == []
