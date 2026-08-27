from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_veyra
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0,
    derive_adaptive_visibility_v0,
)
from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0,
    VisibilityPosture,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.nur_nyr_observation_gate_v1 import (
    NyrObservationGateV1,
    NyrObservationGateV1Error,
)
from koschei.nur_nyr_projection_v2 import NyrProjectionV2Error, project_native_mir_nyr_v2
from koschei.parser import parse


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def veyra():
    return birth_veyra(
        profile_digest=dhex("bank-profile"),
        genesis_digest=dhex("genesis"),
        constitution_digest=dhex("khar-v1"),
        instance_digest=dhex("bank-a"),
        birth_epoch=1,
    )


def decision(*, allowed: bool = True, posture=VisibilityPosture.NORMAL):
    return LearningResistanceDecisionV0(
        "observer",
        d32("session"),
        1,
        10,
        3,
        2,
        0,
        1,
        300,
        posture,
        3 if allowed else 0,
        d32("decision-" + posture.value),
        allowed,
        False,
    )


def envelope(*, tick: int, allowed: bool = True, posture=VisibilityPosture.NORMAL):
    return derive_adaptive_visibility_v0(
        decision=decision(allowed=allowed, posture=posture),
        policy=VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False),
        current_tick=tick,
        rotation_secret_commitment=d32("rotation-secret"),
    )


VEIL = b"v" * 32


def gate(m, v, e, epoch_source):
    return NyrObservationGateV1(m, v, e, VEIL, epoch_source)


def test_gate_renders_only_current_live_surface():
    m = mir()
    v = veyra()
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    rendered = gate(m, v, e, lambda: surface.visibility_epoch).render(surface)

    assert rendered == surface.render()
    assert "treasury" not in rendered
    assert "withdrawal" not in rendered


def test_gate_rejects_integrity_valid_expired_surface_replay():
    m = mir()
    v = veyra()
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrProjectionV2Error, match="expired and cannot be replayed"):
        gate(m, v, e, lambda: surface.expires_before_epoch).render(surface)


def test_gate_rejects_future_surface():
    m = mir()
    v = veyra()
    e = envelope(tick=20)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrProjectionV2Error, match="not valid for the current visibility epoch"):
        gate(m, v, e, lambda: surface.visibility_epoch - 1).render(surface)


def test_gate_rejects_tampered_current_surface():
    m = mir()
    v = veyra()
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)
    forged = replace(
        surface,
        bindings=(replace(surface.bindings[0], root_alias="rforged"), *surface.bindings[1:]),
    )

    with pytest.raises(NyrProjectionV2Error, match="does not match"):
        gate(m, v, e, lambda: surface.visibility_epoch).render(forged)


def test_contained_nur_cannot_open_observation_gate():
    m = mir()
    v = veyra()
    e = envelope(tick=10, allowed=False, posture=VisibilityPosture.CONTAINED)

    with pytest.raises(NyrObservationGateV1Error, match="contained Nur envelope"):
        gate(m, v, e, lambda: e.visibility_epoch)


def test_gate_fails_closed_when_epoch_source_fails():
    m = mir()
    v = veyra()
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    def broken_epoch_source():
        raise RuntimeError("clock unavailable")

    with pytest.raises(NyrObservationGateV1Error, match="failed closed"):
        gate(m, v, e, broken_epoch_source).render(surface)


def test_gate_rejects_boolean_epoch_even_though_bool_is_int_subclass():
    m = mir()
    v = veyra()
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrObservationGateV1Error, match="invalid epoch"):
        gate(m, v, e, lambda: True).render(surface)
