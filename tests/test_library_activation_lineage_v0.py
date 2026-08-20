from dataclasses import replace

import pytest

from koschei.library_activation_freshness_v0 import FreshActivationReceiptV0
from koschei.library_activation_lineage_v0 import (
    ActivationLineageError,
    bind_activation_lineage_v0,
    make_lineage_key_state_v0,
    ratchet_lineage_key_v0,
    verify_lineage_receipt_v0,
)


def d(x: int) -> bytes:
    return bytes([x]) * 32


def fresh(epoch: int) -> FreshActivationReceiptV0:
    return FreshActivationReceiptV0(
        graph_digest=d(1),
        decision_digest=d(2),
        epoch=epoch,
        nonce_digest=d(3),
        receipt_digest=d(4),
        eligible=True,
        authority=False,
    )


def test_lineage_binds_fresh_receipt_and_verifies():
    key=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    receipt=bind_activation_lineage_v0(fresh=fresh(7),key_state=key)
    assert verify_lineage_receipt_v0(receipt=receipt,key_state=key)


def test_epoch_mismatch_fails_closed():
    key=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    with pytest.raises(ActivationLineageError):
        bind_activation_lineage_v0(fresh=fresh(8),key_state=key)


def test_ratchet_changes_key_and_commitment_and_advances_epoch():
    old=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    new=ratchet_lineage_key_v0(old,next_epoch=8)
    assert new.epoch==8
    assert new.key_material!=old.key_material
    assert new.key_commitment!=old.key_commitment
    assert new.previous_commitment==old.key_commitment


def test_old_receipt_does_not_verify_with_new_epoch_key():
    old=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    receipt=bind_activation_lineage_v0(fresh=fresh(7),key_state=old)
    new=ratchet_lineage_key_v0(old,next_epoch=8)
    assert not verify_lineage_receipt_v0(receipt=receipt,key_state=new)


def test_tampered_lineage_digest_rejected():
    key=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    receipt=bind_activation_lineage_v0(fresh=fresh(7),key_state=key)
    bad=replace(receipt,lineage_digest=d(8))
    assert not verify_lineage_receipt_v0(receipt=bad,key_state=key)


def test_previous_lineage_digest_changes_receipt():
    key=make_lineage_key_state_v0(epoch=7,key_material=d(9))
    a=bind_activation_lineage_v0(fresh=fresh(7),key_state=key)
    b=bind_activation_lineage_v0(fresh=fresh(7),key_state=key,previous_lineage_digest=d(6))
    assert a.lineage_digest!=b.lineage_digest
