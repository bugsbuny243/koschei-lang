"""Koschei Library effect attestation quorum v0.

Confirms a committed recovery effect only after independent observers attest to
that exact effect receipt. A single writer or a single trust domain can never
self-confirm. Quorum is bound to the receipt digest, operation digest, epoch,
checkpoint and observation evidence. Conflicting observations fail closed.
This module grants no external authority and performs no I/O.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_recovery_exactly_once_v0 import RecoveryEffectReceiptV0

_CTX=b"koschei.library-effect-attestation-quorum/v0\x00"

class EffectAttestationQuorumError(ValueError): pass

@dataclass(frozen=True,slots=True)
class EffectObservationV0:
    observer_id:str
    trust_domain:str
    receipt_digest:bytes
    operation_digest:bytes
    effect_evidence_digest:bytes
    observed_state_digest:bytes
    observed:bool=True
    authority:bool=False

@dataclass(frozen=True,slots=True)
class EffectConfirmationBarrierV0:
    checkpoint_digest:bytes
    writer_id:str
    epoch:int
    sequence:int
    operation_digest:bytes
    effect_receipt_digest:bytes
    confirming_observer_ids:tuple[str,...]
    confirming_trust_domains:tuple[str,...]
    quorum_threshold:int
    barrier_digest:bytes
    confirmed:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise EffectAttestationQuorumError(f"{name} must be exactly 32 bytes")
    return v


def confirm_recovery_effect_v0(*,receipt:RecoveryEffectReceiptV0,observations:tuple[EffectObservationV0,...],quorum_threshold:int,min_trust_domains:int|None=None)->EffectConfirmationBarrierV0:
    if not isinstance(receipt,RecoveryEffectReceiptV0) or receipt.authority:
        raise EffectAttestationQuorumError("authority-free recovery effect receipt required")
    if receipt.replayed:
        raise EffectAttestationQuorumError("replayed receipt cannot establish fresh effect confirmation")
    if not isinstance(observations,tuple) or not observations:
        raise EffectAttestationQuorumError("non-empty immutable observation tuple required")
    if not isinstance(quorum_threshold,int) or quorum_threshold<1 or quorum_threshold>len(observations):
        raise EffectAttestationQuorumError("quorum threshold outside observation bounds")
    domain_threshold=quorum_threshold if min_trust_domains is None else min_trust_domains
    if not isinstance(domain_threshold,int) or domain_threshold<1 or domain_threshold>quorum_threshold:
        raise EffectAttestationQuorumError("invalid minimum trust-domain threshold")

    expected_receipt=_d32(receipt.receipt_digest,"receipt.receipt_digest")
    expected_op=_d32(receipt.operation_digest,"receipt.operation_digest")
    expected_evidence=_d32(receipt.effect_evidence_digest,"receipt.effect_evidence_digest")
    if expected_evidence==b"\x00"*32:
        raise EffectAttestationQuorumError("fresh effect receipt must contain effect evidence")

    observer_ids=set(); accepted=[]; rejected_conflicts=[]
    for obs in observations:
        if not isinstance(obs,EffectObservationV0) or obs.authority:
            raise EffectAttestationQuorumError("authority-free effect observation required")
        if not obs.observer_id or len(obs.observer_id)>96 or not obs.trust_domain or len(obs.trust_domain)>96:
            raise EffectAttestationQuorumError("invalid observer identity or trust domain")
        if obs.observer_id in observer_ids:
            raise EffectAttestationQuorumError("duplicate observer identity forbidden")
        observer_ids.add(obs.observer_id)
        rd=_d32(obs.receipt_digest,"observation.receipt_digest")
        op=_d32(obs.operation_digest,"observation.operation_digest")
        ev=_d32(obs.effect_evidence_digest,"observation.effect_evidence_digest")
        state=_d32(obs.observed_state_digest,"observation.observed_state_digest")
        if ev==b"\x00"*32 or state==b"\x00"*32:
            raise EffectAttestationQuorumError("observation evidence/state cannot be empty")
        exact=(rd==expected_receipt and op==expected_op and ev==expected_evidence and obs.observed)
        if exact:
            accepted.append(obs)
        elif rd==expected_receipt or op==expected_op:
            rejected_conflicts.append(obs.observer_id)

    if rejected_conflicts:
        raise EffectAttestationQuorumError("conflicting observation for target effect detected")
    if len(accepted)<quorum_threshold:
        raise EffectAttestationQuorumError("effect confirmation quorum not satisfied")
    domains={x.trust_domain for x in accepted}
    if len(domains)<domain_threshold:
        raise EffectAttestationQuorumError("insufficient independent trust domains for confirmation")

    confirming=tuple(sorted(x.observer_id for x in accepted))
    confirming_domains=tuple(sorted(domains))
    h=hashlib.sha3_256(
        _CTX+b"barrier\x00"+receipt.checkpoint_digest+receipt.writer_id.encode()+b"\x00"
        +receipt.epoch.to_bytes(8,"big")+receipt.sequence.to_bytes(8,"big")
        +expected_op+expected_receipt+quorum_threshold.to_bytes(4,"big")+domain_threshold.to_bytes(4,"big")
    )
    for obs in sorted(accepted,key=lambda x:x.observer_id):
        h.update(b"O\x00"+obs.observer_id.encode()+b"\x00"+obs.trust_domain.encode()+b"\x00"+obs.observed_state_digest+obs.effect_evidence_digest)
    return EffectConfirmationBarrierV0(
        receipt.checkpoint_digest,receipt.writer_id,receipt.epoch,receipt.sequence,
        expected_op,expected_receipt,confirming,confirming_domains,quorum_threshold,
        h.digest(),True,False
    )


def verify_effect_confirmation_barrier_v0(*,barrier:EffectConfirmationBarrierV0,receipt:RecoveryEffectReceiptV0,observations:tuple[EffectObservationV0,...],min_trust_domains:int|None=None)->bool:
    if not isinstance(barrier,EffectConfirmationBarrierV0) or barrier.authority or not barrier.confirmed:
        return False
    try:
        rebuilt=confirm_recovery_effect_v0(receipt=receipt,observations=observations,quorum_threshold=barrier.quorum_threshold,min_trust_domains=min_trust_domains)
    except EffectAttestationQuorumError:
        return False
    return rebuilt==barrier
