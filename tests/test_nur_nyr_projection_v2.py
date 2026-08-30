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
from koschei.nur_nyr_projection_v2 import (
    NyrProjectionV2Error,
    project_native_mir_nyr_v2,
    require_live_nyr_surface_v2,
    require_nyr_surface_v2,
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
CANONICAL_ROOTS = ("ka", "vor", "shi", "thal", "nur")
CANONICAL_SUBJECTS = ("treasury", "withdrawal", "evidence", "recovery", "visibility")


def test_nyr_v2_hides_canonical_roots_subjects_and_veyra_identity():
    v = veyra("bank-a")
    surface = project_native_mir_nyr_v2(mir(), v, envelope(tick=10), veil_key=VEIL)
    rendered = surface.render()

    for root in CANONICAL_ROOTS:
        assert root not in rendered
    for subject in CANONICAL_SUBJECTS:
        assert subject not in rendered
    assert v.digest not in rendered
    assert all(binding.root_alias.startswith("r") for binding in surface.bindings)
    assert all(binding.subject_alias.startswith("n") for binding in surface.bindings)
    assert surface.version == 2


def test_nyr_v2_is_deterministic_only_inside_same_living_projection_inputs():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    left = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)
    right = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)
    assert left == right


def test_nyr_v2_rotates_root_and_subject_aliases_across_epoch():
    m = mir()
    v = veyra("bank-a")
    first = project_native_mir_nyr_v2(m, v, envelope(tick=10), veil_key=VEIL)
    second = project_native_mir_nyr_v2(m, v, envelope(tick=20), veil_key=VEIL)

    assert first.visibility_epoch != second.visibility_epoch
    assert tuple(x.root_alias for x in first.bindings) != tuple(x.root_alias for x in second.bindings)
    assert tuple(x.subject_alias for x in first.bindings) != tuple(x.subject_alias for x in second.bindings)
    assert first.surface_digest != second.surface_digest


def test_nyr_v2_rotates_inside_same_epoch_when_observer_session_changes():
    m = mir()
    v = veyra("bank-a")
    left = project_native_mir_nyr_v2(m, v, envelope(tick=10, session="a"), veil_key=VEIL)
    right = project_native_mir_nyr_v2(m, v, envelope(tick=10, session="b"), veil_key=VEIL)

    assert left.visibility_epoch == right.visibility_epoch
    assert left.render() != right.render()


def test_nyr_v2_is_not_transferable_across_customer_veyras():
    m = mir()
    e = envelope(tick=10)
    bank_a = project_native_mir_nyr_v2(m, veyra("bank-a"), e, veil_key=VEIL)
    bank_b = project_native_mir_nyr_v2(m, veyra("bank-b"), e, veil_key=VEIL)

    assert bank_a.render() != bank_b.render()
    assert bank_a.surface_digest != bank_b.surface_digest


def test_contained_nur_exposes_no_nyr_v2_surface():
    with pytest.raises(NyrProjectionV2Error, match="exposes no Nyr v2 surface"):
        project_native_mir_nyr_v2(
            mir(),
            veyra("bank-a"),
            envelope(tick=10, posture=VisibilityPosture.CONTAINED, allowed=False),
            veil_key=VEIL,
        )


def test_visible_nyr_v2_tampering_does_not_become_canonical():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)
    forged = replace(
        surface,
        bindings=(
            replace(surface.bindings[0], root_alias="rforged"),
            *surface.bindings[1:],
        ),
    )
    with pytest.raises(NyrProjectionV2Error, match="does not match"):
        require_nyr_surface_v2(forged, m, v, e, veil_key=VEIL)


def test_live_nyr_v2_accepts_only_its_birth_epoch():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    require_live_nyr_surface_v2(
        surface,
        m,
        v,
        e,
        veil_key=VEIL,
        current_visibility_epoch=surface.visibility_epoch,
    )


def test_live_nyr_v2_rejects_expired_surface_replay():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrProjectionV2Error, match="expired and cannot be replayed"):
        require_live_nyr_surface_v2(
            surface,
            m,
            v,
            e,
            veil_key=VEIL,
            current_visibility_epoch=surface.expires_before_epoch,
        )


def test_live_nyr_v2_rejects_surface_before_its_epoch():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=20)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrProjectionV2Error, match="not valid for the current visibility epoch"):
        require_live_nyr_surface_v2(
            surface,
            m,
            v,
            e,
            veil_key=VEIL,
            current_visibility_epoch=surface.visibility_epoch - 1,
        )


def test_live_nyr_v2_rejects_invalid_epoch_input():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    surface = project_native_mir_nyr_v2(m, v, e, veil_key=VEIL)

    with pytest.raises(NyrProjectionV2Error, match="non-negative integer"):
        require_live_nyr_surface_v2(
            surface,
            m,
            v,
            e,
            veil_key=VEIL,
            current_visibility_epoch=-1,
        )
