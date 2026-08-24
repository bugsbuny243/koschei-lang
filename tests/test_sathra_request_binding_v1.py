from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_sathra_v1 import AxisWitness, KharSathraError, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import (
    SathraRequestBindingError,
    bind_sathra_to_request,
    enforce_sathra_bound_effect,
)


def d(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def proof(m):
    plan = expand_native_sigil_mir(m).library_plan
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=d(step.binding_digest),
            success=True,
        )
        for step in plan.steps
    ]
    return seal_native_sigil_proof(m, receipts)


def galaxy(m, instance="bank-a"):
    v = birth_veyra(
        profile_digest=d("banking-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d(instance),
        birth_epoch=7,
    )
    a = birth_aevra(
        v,
        m,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=d("aevra-birth"),
        birth_epoch=7,
    )
    return v, a


def request(m, payload="payload-a", epoch=7):
    return seal_effect_request(
        m,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d(payload),
        identity_digest=d("operator-7"),
        epoch=epoch,
        nonce_digest=d("nonce-" + payload),
    )


def sathra_for(m, v, a, req):
    axes = ("khor", "sei", "rha", "vaal", "teyr", "esh")
    return seal_sathra(
        AxisWitness(
            axis=axis,
            aevra_digest=a.digest,
            veyra_digest=v.digest,
            event_digest=req.digest,
            reality_digest=m.fingerprint,
            epoch=req.epoch,
            witness_digest=d("witness-" + axis + req.digest),
        )
        for axis in axes
    )


def test_critical_effect_runs_only_with_exact_sathra_request_binding():
    m = mir()
    p = proof(m)
    v, a = galaxy(m)
    req = request(m)
    rb = bind_proof_to_request(m, req, p)
    s = sathra_for(m, v, a, req)
    sb = bind_sathra_to_request(m, v, a, req, s)
    calls = []

    decision, value = enforce_sathra_bound_effect(
        m, v, a, req, p, rb, s, sb, lambda item: calls.append(item.digest) or "done"
    )

    assert decision.decision == "ALLOW"
    assert value == "done"
    assert calls == [req.digest]


def test_sathra_for_one_request_cannot_execute_another_request():
    m = mir()
    p = proof(m)
    v, a = galaxy(m)
    req_a = request(m, "payload-a")
    s = sathra_for(m, v, a, req_a)
    req_b = request(m, "payload-b")
    rb_b = bind_proof_to_request(m, req_b, p)

    with pytest.raises(SathraRequestBindingError, match="different critical event"):
        bind_sathra_to_request(m, v, a, req_b, s)

    # Even a forged binding object cannot convert the old Sathra into the new event.
    old_binding = bind_sathra_to_request(m, v, a, req_a, s)
    with pytest.raises(SathraRequestBindingError):
        enforce_sathra_bound_effect(
            m, v, a, req_b, p, rb_b, s, old_binding, lambda _: "must-not-run"
        )


def test_sathra_cannot_cross_customer_veyra():
    m = mir()
    req = request(m)
    bank_a, aevra_a = galaxy(m, "bank-a")
    bank_b, _ = galaxy(m, "bank-b")
    s = sathra_for(m, bank_a, aevra_a, req)

    with pytest.raises(SathraRequestBindingError, match="different Veyra"):
        bind_sathra_to_request(m, bank_b, aevra_a, req, s)


def test_sathra_cannot_cross_epoch_or_reality():
    m = mir()
    v, a = galaxy(m)
    req = request(m, epoch=7)
    s = sathra_for(m, v, a, req)

    req_next = request(m, payload="next", epoch=8)
    with pytest.raises(SathraRequestBindingError):
        bind_sathra_to_request(m, v, a, req_next, s)

    other_mir = lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur observer;")
    )
    with pytest.raises(SathraRequestBindingError):
        bind_sathra_to_request(other_mir, v, a, req, s)


def test_five_axes_never_create_a_sathra_for_critical_execution():
    m = mir()
    v, a = galaxy(m)
    req = request(m)
    axes = ("khor", "sei", "rha", "vaal", "teyr")
    with pytest.raises(KharSathraError, match="exactly six"):
        seal_sathra(
            AxisWitness(
                axis=axis,
                aevra_digest=a.digest,
                veyra_digest=v.digest,
                event_digest=req.digest,
                reality_digest=m.fingerprint,
                epoch=req.epoch,
                witness_digest=d("witness-" + axis),
            )
            for axis in axes
        )


def test_tampered_sathra_request_binding_fails_closed():
    m = mir()
    v, a = galaxy(m)
    req = request(m)
    s = sathra_for(m, v, a, req)
    binding = bind_sathra_to_request(m, v, a, req, s)
    forged = replace(binding, sathra_digest="0" * 64)
    with pytest.raises(SathraRequestBindingError):
        forged.assert_sealed(m, v, a, req, s)
