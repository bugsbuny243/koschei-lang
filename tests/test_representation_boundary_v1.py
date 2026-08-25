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
from koschei.parser import parse
from koschei.representation_boundary_v1 import (
    RepresentationBoundaryV1Error,
    issue_observable_representation_v1,
    mint_reconstruction_grant_v1,
    reconstruct_canonical_semantics_v1,
    require_representation_equivalence_v1,
    seal_canonical_semantics_v1,
)


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


def decision(session: str = "session"):
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
        VisibilityPosture.NORMAL,
        3,
        d32("decision-" + session),
        True,
        False,
    )


def envelope(*, tick: int, session: str = "session"):
    policy = VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False)
    return derive_adaptive_visibility_v0(
        decision=decision(session),
        policy=policy,
        current_tick=tick,
        rotation_secret_commitment=d32("rotation-secret"),
    )


VEIL = b"v" * 32
RECON = b"r" * 32
CANONICAL_ROOTS = ("ka", "vor", "shi", "thal", "nur")
CANONICAL_SUBJECTS = ("treasury", "withdrawal", "evidence", "recovery", "visibility")


def test_observable_representation_does_not_carry_canonical_semantic_labels():
    m = mir()
    representation = issue_observable_representation_v1(
        m,
        veyra("bank-a"),
        envelope(tick=10),
        veil_key=VEIL,
    )
    visible_values = "\n".join(
        (
            representation.surface.render(),
            representation.surface.surface_digest,
            representation.representation_digest,
        )
    )

    for value in CANONICAL_ROOTS + CANONICAL_SUBJECTS:
        assert value not in visible_values
    for binding in m.bindings:
        assert binding.semantic_domain not in representation.surface.render()
    assert m.fingerprint not in visible_values
    assert m.universe_plan_digest not in visible_values


def test_canonical_seal_is_trusted_side_and_detects_tamper():
    seal = seal_canonical_semantics_v1(mir())
    seal.assert_sealed()

    forged = replace(seal, binding_count=seal.binding_count + 1)
    with pytest.raises(RepresentationBoundaryV1Error, match="seal mismatch"):
        forged.assert_sealed()


def test_same_hidden_world_reproduces_same_representation_and_proves_equivalence():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)

    require_representation_equivalence_v1(
        representation,
        m,
        v,
        e,
        veil_key=VEIL,
    )


def test_representation_tamper_never_becomes_canonical_state():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    forged = replace(
        representation,
        representation_digest="0" * 64,
    )

    with pytest.raises(RepresentationBoundaryV1Error, match="not equivalent"):
        require_representation_equivalence_v1(
            forged,
            m,
            v,
            e,
            veil_key=VEIL,
        )


def test_authorized_reconstruction_returns_hidden_mir_not_an_inverted_surface():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m,
        v,
        e,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    rebuilt = reconstruct_canonical_semantics_v1(
        representation,
        m,
        v,
        e,
        grant,
        purpose="execute",
        current_epoch=e.visibility_epoch,
        veil_key=VEIL,
        reconstruction_key=RECON,
    )
    assert rebuilt is m
    assert rebuilt.fingerprint == m.fingerprint


def test_reconstruction_grant_is_purpose_bound():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m,
        v,
        e,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    with pytest.raises(RepresentationBoundaryV1Error, match="purpose mismatch"):
        reconstruct_canonical_semantics_v1(
            representation,
            m,
            v,
            e,
            grant,
            purpose="inspect",
            current_epoch=e.visibility_epoch,
            veil_key=VEIL,
            reconstruction_key=RECON,
        )


def test_old_epoch_representation_and_grant_die_together():
    m = mir()
    v = veyra("bank-a")
    old = envelope(tick=10)
    new = envelope(tick=20)
    assert old.visibility_epoch != new.visibility_epoch

    representation = issue_observable_representation_v1(
        m,
        v,
        old,
        veil_key=VEIL,
    )
    grant = mint_reconstruction_grant_v1(
        m,
        v,
        old,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    with pytest.raises(RepresentationBoundaryV1Error, match="expired"):
        reconstruct_canonical_semantics_v1(
            representation,
            m,
            v,
            old,
            grant,
            purpose="execute",
            current_epoch=new.visibility_epoch,
            veil_key=VEIL,
            reconstruction_key=RECON,
        )


def test_reconstruction_grant_does_not_transfer_to_another_veyra():
    m = mir()
    source = veyra("bank-a")
    target = veyra("bank-b")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(
        m,
        source,
        e,
        veil_key=VEIL,
    )
    grant = mint_reconstruction_grant_v1(
        m,
        source,
        e,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    with pytest.raises(RepresentationBoundaryV1Error, match="not equivalent"):
        reconstruct_canonical_semantics_v1(
            representation,
            m,
            target,
            e,
            grant,
            purpose="execute",
            current_epoch=e.visibility_epoch,
            veil_key=VEIL,
            reconstruction_key=RECON,
        )


def test_wrong_reconstruction_key_cannot_authorize_hidden_world():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m,
        v,
        e,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )

    with pytest.raises(
        RepresentationBoundaryV1Error,
        match="authorization mismatch",
    ):
        reconstruct_canonical_semantics_v1(
            representation,
            m,
            v,
            e,
            grant,
            purpose="execute",
            current_epoch=e.visibility_epoch,
            veil_key=VEIL,
            reconstruction_key=b"x" * 32,
        )
