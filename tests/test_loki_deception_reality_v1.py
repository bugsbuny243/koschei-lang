import pytest

from koschei.loki_deception_reality_v1 import (
    LokiDeceptionError,
    create_decoy_reality_v1,
    trip_decoy_v1,
    decoy_is_non_authoritative_v1,
)

CANON = b"c" * 32
PAYLOAD = b"p" * 32
OBSERVER = b"o" * 32


def test_decoy_is_bound_to_canonical_reality_payload_and_epoch():
    d = create_decoy_reality_v1(decoy_id="mirror-7",
        canonical_reality_digest=CANON, decoy_payload_digest=PAYLOAD, epoch=7)
    assert len(d.decoy_digest) == 32
    assert d.canonical_reality_digest == CANON
    assert d.epoch == 7


def test_tripwire_is_deterministic_for_same_observation():
    d = create_decoy_reality_v1(decoy_id="mirror-7",
        canonical_reality_digest=CANON, decoy_payload_digest=PAYLOAD, epoch=7)
    a = trip_decoy_v1(d, observer_digest=OBSERVER, action="read")
    b = trip_decoy_v1(d, observer_digest=OBSERVER, action="read")
    assert a.tripwire_digest == b.tripwire_digest


def test_different_action_changes_tripwire_identity():
    d = create_decoy_reality_v1(decoy_id="mirror-7",
        canonical_reality_digest=CANON, decoy_payload_digest=PAYLOAD, epoch=7)
    assert trip_decoy_v1(d, observer_digest=OBSERVER, action="read").tripwire_digest != \
        trip_decoy_v1(d, observer_digest=OBSERVER, action="enumerate").tripwire_digest


def test_decoy_never_becomes_authority_surface():
    d = create_decoy_reality_v1(decoy_id="mirror-7",
        canonical_reality_digest=CANON, decoy_payload_digest=PAYLOAD, epoch=7)
    assert decoy_is_non_authoritative_v1(d)


def test_invalid_digests_fail_closed():
    with pytest.raises(LokiDeceptionError):
        create_decoy_reality_v1(decoy_id="x", canonical_reality_digest=b"bad",
            decoy_payload_digest=PAYLOAD, epoch=1)
