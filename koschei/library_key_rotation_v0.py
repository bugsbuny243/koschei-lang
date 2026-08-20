"""Koschei Library compromise-aware key rotation ceremony v0.

Provides explicit, bounded overlap between an old lineage key and a replacement
key, with graph/epoch binding, compromise recovery and deterministic closure.
This module does not grant runtime authority; it only derives rotation receipts.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac

from .library_activation_lineage_v0 import LineageKeyStateV0, LineageReceiptV0

_CTX=b"koschei.library-key-rotation/v0\x00"

class KeyRotationError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RotationPlanV0:
    graph_digest:bytes
    from_epoch:int
    to_epoch:int
    old_commitment:bytes
    new_commitment:bytes
    overlap_until_epoch:int
    compromise_recovery:bool
    plan_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RotationReceiptV0:
    plan_digest:bytes
    previous_lineage_digest:bytes
    old_authenticator:bytes
    new_authenticator:bytes
    receipt_digest:bytes
    closed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32: raise KeyRotationError(f"{name} must be exactly 32 bytes")
    return v


def make_rotation_plan_v0(*,graph_digest:bytes,old_state:LineageKeyStateV0,new_state:LineageKeyStateV0,overlap_until_epoch:int,compromise_recovery:bool=False)->RotationPlanV0:
    gd=_d32(graph_digest,"graph_digest")
    if not isinstance(old_state,LineageKeyStateV0) or old_state.authority: raise KeyRotationError("old lineage state required")
    if not isinstance(new_state,LineageKeyStateV0) or new_state.authority: raise KeyRotationError("new lineage state required")
    if new_state.epoch<=old_state.epoch: raise KeyRotationError("replacement key must advance epoch")
    if not isinstance(overlap_until_epoch,int) or overlap_until_epoch<new_state.epoch: raise KeyRotationError("overlap cannot end before replacement epoch")
    if overlap_until_epoch-new_state.epoch>2: raise KeyRotationError("rotation overlap exceeds hard safety window")
    material=(_CTX+b"plan\x00"+gd+old_state.epoch.to_bytes(8,"big")+new_state.epoch.to_bytes(8,"big")+old_state.key_commitment+new_state.key_commitment+overlap_until_epoch.to_bytes(8,"big")+(b"\x01" if compromise_recovery else b"\x00"))
    return RotationPlanV0(gd,old_state.epoch,new_state.epoch,old_state.key_commitment,new_state.key_commitment,overlap_until_epoch,compromise_recovery,hashlib.sha3_256(material).digest(),False)


def close_rotation_v0(*,plan:RotationPlanV0,previous:LineageReceiptV0,old_state:LineageKeyStateV0,new_state:LineageKeyStateV0,current_epoch:int)->RotationReceiptV0:
    if not isinstance(plan,RotationPlanV0) or plan.authority: raise KeyRotationError("authority-free rotation plan required")
    if not isinstance(previous,LineageReceiptV0) or previous.authority: raise KeyRotationError("previous lineage receipt required")
    if not isinstance(old_state,LineageKeyStateV0) or not isinstance(new_state,LineageKeyStateV0): raise KeyRotationError("lineage key states required")
    if current_epoch<new_state.epoch or current_epoch>plan.overlap_until_epoch: raise KeyRotationError("rotation attempted outside overlap window")
    expected=make_rotation_plan_v0(graph_digest=plan.graph_digest,old_state=old_state,new_state=new_state,overlap_until_epoch=plan.overlap_until_epoch,compromise_recovery=plan.compromise_recovery)
    if expected!=plan: raise KeyRotationError("rotation plan drift detected")
    if previous.graph_digest!=plan.graph_digest: raise KeyRotationError("lineage/rotation graph mismatch")
    base=_CTX+b"close\x00"+plan.plan_digest+previous.lineage_digest+current_epoch.to_bytes(8,"big")
    old_auth=hmac.new(old_state.key_material,base+b"old",hashlib.sha3_256).digest()
    new_auth=hmac.new(new_state.key_material,base+b"new",hashlib.sha3_256).digest()
    receipt_digest=hashlib.sha3_256(base+old_auth+new_auth).digest()
    return RotationReceiptV0(plan.plan_digest,previous.lineage_digest,old_auth,new_auth,receipt_digest,True,False)


def verify_rotation_receipt_v0(*,receipt:RotationReceiptV0,plan:RotationPlanV0,previous:LineageReceiptV0,old_state:LineageKeyStateV0,new_state:LineageKeyStateV0,current_epoch:int)->bool:
    if not isinstance(receipt,RotationReceiptV0) or receipt.authority or not receipt.closed: return False
    try:
        expected=close_rotation_v0(plan=plan,previous=previous,old_state=old_state,new_state=new_state,current_epoch=current_epoch)
    except KeyRotationError:
        return False
    return hmac.compare_digest(receipt.receipt_digest,expected.receipt_digest) and hmac.compare_digest(receipt.old_authenticator,expected.old_authenticator) and hmac.compare_digest(receipt.new_authenticator,expected.new_authenticator)
