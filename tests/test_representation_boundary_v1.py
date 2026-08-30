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
from koschei.native_sigil_request_binding_v1 import seal_effect_request
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


def request(m, e, tag: str = "42"):
    return seal_effect_request(
        m,
        effect_id="withdrawal:" + tag,
        subject="withdrawal",
        operation="signer.execute",
        request_digest=dhex("payload-" + tag),
        identity_digest=dhex("identity-" + tag),
        epoch=e.visibility_epoch,
        nonce_digest=dhex("nonce-" + tag),
    )


VEIL = b"v" * 32
RECON = b"r" * 32
CANONICAL_ROOTS = ("ka", "vor", "shi", "thal", "nur")
CANONICAL_SUBJECTS = ("treasury", "withdrawal", "evidence", "recovery", "visibility")


def test_observable_representation_does_not_carry_canonical_semantic_labels():
    m = mir()
    representation = issue_observable_representation_v1(
        m, veyra("bank-a"), envelope(tick=10), veil_key=VEIL
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
    require_representation_equivalence_v1(representation, m, v, e, veil_key=VEIL)


def test_representation_tamper_never_becomes_canonical_state():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    forged = replace(representation, representation_digest="0" * 64)
    with pytest.raises(RepresentationBoundaryV1Error, match="not equivalent"):
        require_representation_equivalence_v1(forged, m, v, e, veil_key=VEIL)


def test_authorized_reconstruction_is_exact_request_bound():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    req = request(m, e)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, v, e, req,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )
    rebuilt = reconstruct_canonical_semantics_v1(
        representation, m, v, e, grant, req,
        purpose="execute",
        current_epoch=e.visibility_epoch,
        veil_key=VEIL,
        reconstruction_key=RECON,
    )
    assert rebuilt is m
    assert rebuilt.fingerprint == m.fingerprint
    assert req.digest not in repr(grant)


def test_reconstruction_grant_rejects_another_request_same_world_epoch_and_purpose():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    req_a = request(m, e, "42")
    req_b = request(m, e, "43")
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, v, e, req_a,
        grant_id="compile-run-1",
        purpose="execute",
        reconstruction_key=RECON,
    )
    with pytest.raises(RepresentationBoundaryV1Error, match="canonical request mismatch"):
        reconstruct_canonical_semantics_v1(
            representation, m, v, e, grant, req_b,
            purpose="execute",
            current_epoch=e.visibility_epoch,
            veil_key=VEIL,
            reconstruction_key=RECON,
        )


def test_request_binding_rotates_across_veyra_and_session_context():
    m = mir()
    e1 = envelope(tick=10, session="one")
    e2 = envelope(tick=10, session="two")
    req1 = request(m, e1)
    req2 = request(m, e2)
    g1 = mint_reconstruction_grant_v1(
        m, veyra("bank-a"), e1, req1,
        grant_id="same", purpose="execute", reconstruction_key=RECON,
    )
    g2 = mint_reconstruction_grant_v1(
        m, veyra("bank-a"), e2, req2,
        grant_id="same", purpose="execute", reconstruction_key=RECON,
    )
    g3 = mint_reconstruction_grant_v1(
        m, veyra("bank-b"), e1, req1,
        grant_id="same", purpose="execute", reconstruction_key=RECON,
    )
    assert g1.request_binding != g2.request_binding
    assert g1.request_binding != g3.request_binding


def test_reconstruction_grant_is_purpose_bound():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    req = request(m, e)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, v, e, req,
        grant_id="compile-run-1", purpose="execute", reconstruction_key=RECON,
    )
    with pytest.raises(RepresentationBoundaryV1Error, match="purpose mismatch"):
        reconstruct_canonical_semantics_v1(
            representation, m, v, e, grant, req,
            purpose="inspect", current_epoch=e.visibility_epoch,
            veil_key=VEIL, reconstruction_key=RECON,
        )


def test_old_epoch_representation_and_grant_die_together():
    m = mir()
    v = veyra("bank-a")
    old = envelope(tick=10)
    new = envelope(tick=20)
    assert old.visibility_epoch != new.visibility_epoch
    req = request(m, old)
    representation = issue_observable_representation_v1(m, v, old, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, v, old, req,
        grant_id="compile-run-1", purpose="execute", reconstruction_key=RECON,
    )
    with pytest.raises(RepresentationBoundaryV1Error, match="expired"):
        reconstruct_canonical_semantics_v1(
            representation, m, v, old, grant, req,
            purpose="execute", current_epoch=new.visibility_epoch,
            veil_key=VEIL, reconstruction_key=RECON,
        )


def test_reconstruction_grant_does_not_transfer_to_another_veyra():
    m = mir()
    source = veyra("bank-a")
    target = veyra("bank-b")
    e = envelope(tick=10)
    req = request(m, e)
    representation = issue_observable_representation_v1(m, source, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, source, e, req,
        grant_id="compile-run-1", purpose="execute", reconstruction_key=RECON,
    )
    with pytest.raises(RepresentationBoundaryV1Error, match="not equivalent"):
        reconstruct_canonical_semantics_v1(
            representation, m, target, e, grant, req,
            purpose="execute", current_epoch=e.visibility_epoch,
            veil_key=VEIL, reconstruction_key=RECON,
        )


def test_wrong_reconstruction_key_cannot_authorize_hidden_world():
    m = mir()
    v = veyra("bank-a")
    e = envelope(tick=10)
    req = request(m, e)
    representation = issue_observable_representation_v1(m, v, e, veil_key=VEIL)
    grant = mint_reconstruction_grant_v1(
        m, v, e, req,
        grant_id="compile-run-1", purpose="execute", reconstruction_key=RECON,
    )
    with pytest.raises(RepresentationBoundaryV1Error, match="canonical request mismatch|context mismatch|authorization mismatch"):
        reconstruct_canonical_semantics_v1(
            representation, m, v, e, grant, req,
            purpose="execute", current_epoch=e.visibility_epoch,
            veil_key=VEIL, reconstruction_key=b"x" * 32,
        )
