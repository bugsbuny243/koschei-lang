from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_atomic_execution_coordinator_v1 import (
    AtomicExecutionCoordinator,
    AtomicExecutionCoordinatorError,
)
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import (
    bind_sathra_to_request,
    enforce_atomic_sathra_bound_effect,
)
from koschei.universe_state_machine_v1 import initial_universe_state


def d(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def proof(m, *, fail_obligation=None):
    plan = expand_native_sigil_mir(m).library_plan
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=d(step.binding_digest),
            success=step.obligation != fail_obligation,
        )
        for step in plan.steps
    ]
    return seal_native_sigil_proof(m, receipts)


def galaxy(m):
    v = birth_veyra(
        profile_digest=d("banking-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d("bank-a"),
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


def request(m, payload="payload-a"):
    return seal_effect_request(
        m,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d(payload),
        identity_digest=d("identity"),
        epoch=7,
        nonce_digest=d("nonce-" + payload),
    )


def sathra_for(m, v, a, req):
    return seal_sathra(
        AxisWitness(
            axis=axis,
            aevra_digest=a.digest,
            veyra_digest=v.digest,
            event_digest=req.digest,
            reality_digest=m.fingerprint,
            epoch=req.epoch,
            witness_digest=d(f"{axis}:{req.digest}"),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )


def bundle(fail_obligation=None):
    m = mir()
    p = proof(m, fail_obligation=fail_obligation)
    v, a = galaxy(m)
    req = request(m)
    rb = bind_proof_to_request(m, req, p)
    s = sathra_for(m, v, a, req)
    sb = bind_sathra_to_request(m, v, a, req, s)
    return m, p, v, a, req, rb, s, sb


def test_atomic_sathra_event_commits_once_and_cannot_replay():
    m, p, v, a, req, rb, s, sb = bundle()
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        with AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3") as coordinator:
            coordinator.initialize(state)
            decision, value, claim = enforce_atomic_sathra_bound_effect(
                m, v, a, req, p, rb, s, sb, coordinator,
                lambda item: calls.append(item.digest) or "done",
            )
            assert decision.decision == "ALLOW"
            assert value == "done"
            assert claim.state == "COMMITTED"
            assert calls == [req.digest]

            with pytest.raises(AtomicExecutionCoordinatorError):
                enforce_atomic_sathra_bound_effect(
                    m, v, a, req, p, rb, s, sb, coordinator,
                    lambda item: calls.append(item.digest) or "must-not-run",
                )
            assert calls == [req.digest]


def test_effect_exception_becomes_uncertain_and_still_blocks_replay():
    m, p, v, a, req, rb, s, sb = bundle()
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3") as coordinator:
            coordinator.initialize(state)

            def boom(_):
                raise RuntimeError("effect boundary failed")

            with pytest.raises(RuntimeError, match="effect boundary failed"):
                enforce_atomic_sathra_bound_effect(
                    m, v, a, req, p, rb, s, sb, coordinator, boom
                )
            with pytest.raises(AtomicExecutionCoordinatorError):
                enforce_atomic_sathra_bound_effect(
                    m, v, a, req, p, rb, s, sb, coordinator, lambda _: "retry"
                )


def test_denied_sathra_event_is_finalized_without_running_effect():
    m, p, v, a, req, rb, s, sb = bundle("derive-least-authority")
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        with AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3") as coordinator:
            coordinator.initialize(state)
            decision, value, claim = enforce_atomic_sathra_bound_effect(
                m, v, a, req, p, rb, s, sb, coordinator,
                lambda _: calls.append(1),
            )
            assert decision.decision == "DENY"
            assert value is None
            assert claim.state == "REJECTED"
            assert calls == []


def test_containment_decision_finalizes_sathra_as_contained():
    m, p, v, a, req, rb, s, sb = bundle("fence-stale-writers")
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3") as coordinator:
            coordinator.initialize(state)
            decision, value, claim = enforce_atomic_sathra_bound_effect(
                m, v, a, req, p, rb, s, sb, coordinator, lambda _: "must-not-run"
            )
            assert decision.decision == "CONTAIN"
            assert value is None
            assert claim.state == "CONTAINED"
