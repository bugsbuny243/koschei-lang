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
from koschei.nur_nyr_projection_v1 import (
    NyrProjectionError,
    project_native_mir_nyr,
    require_nyr_surface,
)
from koschei.parser import parse


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def veyra(instance: str):
    return birth_veyra(
        profile_digest=dhex("bank-profile"),
        genesis_digest=dhex("genesis"),
        constitution_digest=dhex("khar-v1"),
        instance_digest=dhex(instance),
        birth_epoch=1,
    )


def decision(session: str = "session", posture=VisibilityPosture.NORMAL, allowed=True):
    return LearningResistanceDecisionV0(
        "observer",
        d32(session),
        1,
        10,
        3,
        2,
        0,
        1,
        300,
        posture,
        3 if allowed else 0,
        d32("decision-" + session + posture.value),
        allowed,
        False,
    )


def envelope(*, tick: int, session: str = "session", posture=VisibilityPosture.NORMAL, allowed=True):
    policy = VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False)
    return derive_adaptive_visibility_v0(
        decision=decision(session, posture, allowed),
        policy=policy,
        current_tick=tick,
        rotation_secret_commitment=d32("rotation-secret"),
    )


VEIL = b"v" * 32


def test_nyr_keeps_sigils_but_hides_canonical_subjects():
    surface = project_native_mir_nyr(mir(), veyra("bank-a"), envelope(tick=10), veil_key=VEIL)
    rendered = surface.render()
    for sigil in ("ka", "vor", "shi", "thal", "nur"):
        assert f"{sigil} " in rendered
    for subject in ("treasury", "withdrawal", "evidence", "recovery", "visibility"):
        assert subject not in rendered
    assert all(binding.alias.startswith("n") for binding in surface.bindings)


def test_same_living_inputs_are_deterministic_inside_one_visibility_epoch():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    left = project_native_mir_nyr(m, v, e, veil_key=VEIL)
    right = project_native_mir_nyr(m, v, e, veil_key=VEIL)
    assert left == right


def test_nyr_rotates_when_visibility_epoch_changes():
    m = mir()
    v = veyra("bank-a")
    first = project_native_mir_nyr(m, v, envelope(tick=10), veil_key=VEIL)
    second = project_native_mir_nyr(m, v, envelope(tick=20), veil_key=VEIL)
    assert first.visibility_epoch != second.visibility_epoch
    assert first.render() != second.render()
    assert first.surface_digest != second.surface_digest


def test_same_language_and_mir_project_differently_across_customer_veyras():
    m = mir()
    e = envelope(tick=10)
    bank_a = project_native_mir_nyr(m, veyra("bank-a"), e, veil_key=VEIL)
    bank_b = project_native_mir_nyr(m, veyra("bank-b"), e, veil_key=VEIL)
    assert bank_a.render() != bank_b.render()


def test_observer_session_change_rotates_surface_inside_same_tick():
    m = mir()
    v = veyra("bank-a")
    left = project_native_mir_nyr(m, v, envelope(tick=10, session="a"), veil_key=VEIL)
    right = project_native_mir_nyr(m, v, envelope(tick=10, session="b"), veil_key=VEIL)
    assert left.render() != right.render()


def test_contained_nur_exposes_no_nyr_surface():
    with pytest.raises(NyrProjectionError, match="exposes no Nyr surface"):
        project_native_mir_nyr(
            mir(),
            veyra("bank-a"),
            envelope(tick=10, posture=VisibilityPosture.CONTAINED, allowed=False),
            veil_key=VEIL,
        )


def test_visible_nyr_tampering_does_not_become_canonical():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    surface = project_native_mir_nyr(m, v, e, veil_key=VEIL)
    forged = replace(surface, bindings=(replace(surface.bindings[0], alias="nforged"), *surface.bindings[1:]))
    with pytest.raises(NyrProjectionError, match="does not match"):
        require_nyr_surface(forged, m, v, e, veil_key=VEIL)
