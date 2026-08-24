from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.morth_black_hole_v1 import (
    DurableBlackHole,
    MorthError,
    enforce_living_atomic_sathra_effect,
)
from koschei.native_sigil_atomic_execution_coordinator_v1 import AtomicExecutionCoordinator
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import bind_sathra_to_request
from koschei.universe_state_machine_v1 import initial_universe_state


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def veyra():
    return birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )


def aevra(v, m, *, evidence="birth-a", epoch=7):
    return birth_aevra(
        v,
        m,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=d(evidence),
        birth_epoch=epoch,
    )


def proof(m):
    plan = expand_native_sigil_mir(m).library_plan
    return seal_native_sigil_proof(
        m,
        [
            make_receipt(
                activation_step_id=step.activation_step_id,
                obligation=step.obligation,
                subsystem=step.subsystem,
                proof_kind=step.proof_kind,
                evidence_digest=d(step.binding_digest),
                success=True,
            )
            for step in plan.steps
        ],
    )


def request(m):
    return seal_effect_request(
        m,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d("payload"),
        identity_digest=d("identity"),
        epoch=7,
        nonce_digest=d("nonce"),
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
            witness_digest=d(axis + req.digest),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )


def test_event_horizon_is_durable_and_has_no_unbury_api():
    m = mir()
    v = veyra()
    a = aevra(v, m)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "black-hole.sqlite3"
        black = DurableBlackHole(path)
        record = black.enter_event_horizon(
            a, v, m, death_epoch=7, cause_digest=d("cause"), evidence_digest=d("evidence")
        )
        assert record.death_epoch == 7
        assert black.is_morth(a, v)
        assert not hasattr(black, "unbury")
        assert not hasattr(black, "delete")
        black.close()

        black = DurableBlackHole(path)
        try:
            assert black.is_morth(a, v)
            with pytest.raises(MorthError, match="no living future"):
                black.require_living(a, v, m)
        finally:
            black.close()


def test_same_aevra_cannot_cross_event_horizon_twice():
    m = mir()
    v = veyra()
    a = aevra(v, m)
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black:
            black.enter_event_horizon(
                a, v, m, death_epoch=7, cause_digest=d("cause"), evidence_digest=d("evidence")
            )
            with pytest.raises(MorthError, match="already crossed"):
                black.enter_event_horizon(
                    a, v, m, death_epoch=8, cause_digest=d("cause-2"), evidence_digest=d("evidence-2")
                )


def test_rebirth_requires_distinct_aevra_born_after_morth():
    m = mir()
    v = veyra()
    old = aevra(v, m, evidence="old", epoch=7)
    new = aevra(v, m, evidence="new", epoch=8)
    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black:
            black.enter_event_horizon(
                old, v, m, death_epoch=7, cause_digest=d("cause"), evidence_digest=d("evidence")
            )
            black.require_rebirth_not_resurrection(old, new, v, m, m)
            with pytest.raises(MorthError, match="resurrect"):
                black.require_rebirth_not_resurrection(old, old, v, m, m)


def test_morth_aevra_cannot_execute_even_with_valid_sathra():
    m = mir()
    v = veyra()
    a = aevra(v, m)
    p = proof(m)
    req = request(m)
    rb = bind_proof_to_request(m, req, p)
    s = sathra_for(m, v, a, req)
    sb = bind_sathra_to_request(m, v, a, req, s)
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    calls = []

    with tempfile.TemporaryDirectory() as directory:
        with DurableBlackHole(Path(directory) / "black-hole.sqlite3") as black, AtomicExecutionCoordinator(
            Path(directory) / "execution.sqlite3"
        ) as coordinator:
            coordinator.initialize(state)
            black.enter_event_horizon(
                a, v, m, death_epoch=7, cause_digest=d("cause"), evidence_digest=d("evidence")
            )
            with pytest.raises(MorthError, match="no living future"):
                enforce_living_atomic_sathra_effect(
                    black,
                    m,
                    v,
                    a,
                    req,
                    p,
                    rb,
                    s,
                    sb,
                    coordinator,
                    lambda _: calls.append(1),
                )
            assert calls == []
