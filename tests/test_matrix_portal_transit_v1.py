import pytest

from koschei.matrix_portal_transit_v1 import (
    MatrixPortalTransitError,
    create_portal_transit_proof_v1,
    portal_matches_reality_v1,
)
from koschei.wanda_reality_integrity_v1 import commit_reality_v1


def reality(name, epoch, state_byte, auth_byte, prev=b"\x00" * 32):
    return commit_reality_v1(
        reality_id=name,
        epoch=epoch,
        state_digest=state_byte * 32,
        authority_digest=auth_byte * 32,
        previous_commitment=prev,
    )


def test_portal_binds_both_realities_payload_effect_target_and_epoch():
    src = reality("AEGIS", 4, b"s", b"a")
    dst = reality("FORGE", 9, b"d", b"b")
    proof = create_portal_transit_proof_v1(
        source=src, destination=dst, payload_digest=b"p" * 32,
        effect="compile", target_digest=b"t" * 32, epoch=11,
    )
    assert portal_matches_reality_v1(
        proof, source=src, destination=dst, payload_digest=b"p" * 32,
        effect="compile", target_digest=b"t" * 32, epoch=11,
    )
    assert len(proof.transit_digest) == 32


def test_payload_or_target_substitution_breaks_portal_identity():
    src = reality("AEGIS", 4, b"s", b"a")
    dst = reality("FORGE", 9, b"d", b"b")
    proof = create_portal_transit_proof_v1(source=src, destination=dst,
        payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)
    assert not portal_matches_reality_v1(proof, source=src, destination=dst,
        payload_digest=b"x" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)
    assert not portal_matches_reality_v1(proof, source=src, destination=dst,
        payload_digest=b"p" * 32, effect="compile", target_digest=b"x" * 32, epoch=11)


def test_reality_state_change_invalidates_old_portal():
    src = reality("AEGIS", 4, b"s", b"a")
    dst = reality("FORGE", 9, b"d", b"b")
    proof = create_portal_transit_proof_v1(source=src, destination=dst,
        payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)
    changed_src = reality("AEGIS", 4, b"z", b"a")
    assert not portal_matches_reality_v1(proof, source=changed_src, destination=dst,
        payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)


def test_same_reality_cannot_fake_cross_reality_portal():
    src = reality("AEGIS", 4, b"s", b"a")
    with pytest.raises(MatrixPortalTransitError):
        create_portal_transit_proof_v1(source=src, destination=src,
            payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)


def test_portal_is_not_execution_or_authority():
    src = reality("AEGIS", 4, b"s", b"a")
    dst = reality("FORGE", 9, b"d", b"b")
    proof = create_portal_transit_proof_v1(source=src, destination=dst,
        payload_digest=b"p" * 32, effect="compile", target_digest=b"t" * 32, epoch=11)
    assert not hasattr(proof, "execute")
    assert not hasattr(proof, "grant")
    assert not hasattr(proof, "send")
