import hashlib
import pytest

from koschei.library_activation_lineage_v0 import (
    make_lineage_key_state_v0,
    bind_activation_lineage_v0,
)
from koschei.library_activation_freshness_v0 import FreshActivationReceiptV0
from koschei.library_key_rotation_v0 import (
    KeyRotationError,
    make_rotation_plan_v0,
    close_rotation_v0,
    verify_rotation_receipt_v0,
)


def d(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def fresh(epoch: int) -> FreshActivationReceiptV0:
    return FreshActivationReceiptV0(d("graph"), d("decision"), epoch, d(f"nonce-{epoch}"), d(f"receipt-{epoch}"), True, False)


def test_rotation_closes_with_dual_authentication():
    old = make_lineage_key_state_v0(epoch=7, key_material=b"a"*32)
    prev = bind_activation_lineage_v0(fresh=fresh(7), key_state=old)
    new = make_lineage_key_state_v0(epoch=8, key_material=b"b"*32, previous_commitment=old.key_commitment)
    plan = make_rotation_plan_v0(graph_digest=d("graph"), old_state=old, new_state=new, overlap_until_epoch=9)
    receipt = close_rotation_v0(plan=plan, previous=prev, old_state=old, new_state=new, current_epoch=8)
    assert verify_rotation_receipt_v0(receipt=receipt, plan=plan, previous=prev, old_state=old, new_state=new, current_epoch=8)


def test_rotation_rejects_long_overlap():
    old = make_lineage_key_state_v0(epoch=1, key_material=b"a"*32)
    new = make_lineage_key_state_v0(epoch=2, key_material=b"b"*32, previous_commitment=old.key_commitment)
    with pytest.raises(KeyRotationError):
        make_rotation_plan_v0(graph_digest=d("graph"), old_state=old, new_state=new, overlap_until_epoch=5)


def test_rotation_rejects_graph_drift():
    old = make_lineage_key_state_v0(epoch=3, key_material=b"a"*32)
    prev = bind_activation_lineage_v0(fresh=fresh(3), key_state=old)
    new = make_lineage_key_state_v0(epoch=4, key_material=b"b"*32, previous_commitment=old.key_commitment)
    plan = make_rotation_plan_v0(graph_digest=d("other"), old_state=old, new_state=new, overlap_until_epoch=4)
    with pytest.raises(KeyRotationError):
        close_rotation_v0(plan=plan, previous=prev, old_state=old, new_state=new, current_epoch=4)


def test_rotation_rejects_outside_window():
    old = make_lineage_key_state_v0(epoch=10, key_material=b"a"*32)
    prev = bind_activation_lineage_v0(fresh=fresh(10), key_state=old)
    new = make_lineage_key_state_v0(epoch=11, key_material=b"b"*32, previous_commitment=old.key_commitment)
    plan = make_rotation_plan_v0(graph_digest=d("graph"), old_state=old, new_state=new, overlap_until_epoch=11)
    with pytest.raises(KeyRotationError):
        close_rotation_v0(plan=plan, previous=prev, old_state=old, new_state=new, current_epoch=12)


def test_rotation_detects_replacement_key_drift():
    old = make_lineage_key_state_v0(epoch=20, key_material=b"a"*32)
    prev = bind_activation_lineage_v0(fresh=fresh(20), key_state=old)
    new = make_lineage_key_state_v0(epoch=21, key_material=b"b"*32, previous_commitment=old.key_commitment)
    plan = make_rotation_plan_v0(graph_digest=d("graph"), old_state=old, new_state=new, overlap_until_epoch=21)
    wrong_new = make_lineage_key_state_v0(epoch=21, key_material=b"c"*32, previous_commitment=old.key_commitment)
    with pytest.raises(KeyRotationError):
        close_rotation_v0(plan=plan, previous=prev, old_state=old, new_state=wrong_new, current_epoch=21)
