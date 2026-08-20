"""Koschei Library activation lineage v0.

Adds epoch-key ratcheting and receipt lineage on top of fresh activation receipts.
Security property: if old epoch keys are erased after ratcheting, compromise of a
later epoch key does not reveal earlier epoch keys. This module never treats the
ratchet as authority by itself; it only binds activation receipts into a lineage.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .library_activation_freshness_v0 import FreshActivationReceiptV0

_CTX=b"koschei.library-activation-lineage/v0\x00"

class ActivationLineageError(ValueError): pass

@dataclass(frozen=True,slots=True)
class LineageKeyStateV0:
    epoch:int
    key_material:bytes
    key_commitment:bytes
    previous_commitment:bytes
    state_digest:bytes
    authority:bool=False

@dataclass(frozen=True,slots=True)
class LineageReceiptV0:
    graph_digest:bytes
    activation_receipt_digest:bytes
    epoch:int
    key_commitment:bytes
    previous_lineage_digest:bytes
    lineage_digest:bytes
    authenticator:bytes
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise ActivationLineageError(f"{name} must be exactly 32 bytes")
    return v


def _state_digest(epoch:int,key_commitment:bytes,previous_commitment:bytes)->bytes:
    return hashlib.sha3_256(
        _CTX+b"state\x00"+epoch.to_bytes(8,"big")
        +_d32(key_commitment,"key_commitment")
        +_d32(previous_commitment,"previous_commitment")
    ).digest()


def make_lineage_key_state_v0(*,epoch:int,key_material:bytes,previous_commitment:bytes|None=None)->LineageKeyStateV0:
    if not isinstance(epoch,int) or epoch<1:
        raise ActivationLineageError("epoch must be positive")
    if not isinstance(key_material,bytes) or len(key_material)<32:
        raise ActivationLineageError("lineage key material must be at least 256 bits")
    prev=b"\x00"*32 if previous_commitment is None else _d32(previous_commitment,"previous_commitment")
    commitment=hashlib.sha3_256(_CTX+b"key\x00"+epoch.to_bytes(8,"big")+key_material+prev).digest()
    return LineageKeyStateV0(epoch,key_material,commitment,prev,_state_digest(epoch,commitment,prev),False)


def ratchet_lineage_key_v0(state:LineageKeyStateV0,*,next_epoch:int)->LineageKeyStateV0:
    if not isinstance(state,LineageKeyStateV0) or state.authority:
        raise ActivationLineageError("authority-free lineage key state required")
    if not isinstance(next_epoch,int) or next_epoch<=state.epoch:
        raise ActivationLineageError("lineage epoch must advance monotonically")
    # One-way ratchet. Forward-security depends on callers erasing state.key_material
    # after this function returns the next state.
    next_key=hmac.new(
        state.key_material,
        _CTX+b"ratchet\x00"+state.key_commitment+next_epoch.to_bytes(8,"big"),
        hashlib.sha3_256,
    ).digest()
    return make_lineage_key_state_v0(
        epoch=next_epoch,
        key_material=next_key,
        previous_commitment=state.key_commitment,
    )


def bind_activation_lineage_v0(*,fresh:FreshActivationReceiptV0,key_state:LineageKeyStateV0,previous_lineage_digest:bytes|None=None)->LineageReceiptV0:
    if not isinstance(fresh,FreshActivationReceiptV0) or fresh.authority or not fresh.eligible:
        raise ActivationLineageError("eligible authority-free fresh activation receipt required")
    if not isinstance(key_state,LineageKeyStateV0) or key_state.authority:
        raise ActivationLineageError("authority-free lineage key state required")
    if fresh.epoch!=key_state.epoch:
        raise ActivationLineageError("fresh activation epoch must match lineage key epoch")
    prev=b"\x00"*32 if previous_lineage_digest is None else _d32(previous_lineage_digest,"previous_lineage_digest")
    material=(
        _CTX+b"receipt\x00"+fresh.graph_digest+fresh.receipt_digest
        +fresh.epoch.to_bytes(8,"big")+key_state.key_commitment+prev
    )
    lineage_digest=hashlib.sha3_256(material).digest()
    authenticator=hmac.new(key_state.key_material,material+lineage_digest,hashlib.sha3_256).digest()
    return LineageReceiptV0(
        fresh.graph_digest,fresh.receipt_digest,fresh.epoch,key_state.key_commitment,
        prev,lineage_digest,authenticator,False
    )


def verify_lineage_receipt_v0(*,receipt:LineageReceiptV0,key_state:LineageKeyStateV0)->bool:
    if not isinstance(receipt,LineageReceiptV0) or receipt.authority:
        return False
    if not isinstance(key_state,LineageKeyStateV0) or key_state.authority:
        return False
    if receipt.epoch!=key_state.epoch or receipt.key_commitment!=key_state.key_commitment:
        return False
    try:
        _d32(receipt.graph_digest,"graph_digest")
        _d32(receipt.activation_receipt_digest,"activation_receipt_digest")
        _d32(receipt.previous_lineage_digest,"previous_lineage_digest")
        _d32(receipt.lineage_digest,"lineage_digest")
        _d32(receipt.authenticator,"authenticator")
    except ActivationLineageError:
        return False
    material=(
        _CTX+b"receipt\x00"+receipt.graph_digest+receipt.activation_receipt_digest
        +receipt.epoch.to_bytes(8,"big")+receipt.key_commitment+receipt.previous_lineage_digest
    )
    expected_digest=hashlib.sha3_256(material).digest()
    if not hmac.compare_digest(expected_digest,receipt.lineage_digest):
        return False
    expected_auth=hmac.new(key_state.key_material,material+expected_digest,hashlib.sha3_256).digest()
    return hmac.compare_digest(expected_auth,receipt.authenticator)
