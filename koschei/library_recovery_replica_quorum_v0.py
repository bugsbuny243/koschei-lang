"""Koschei Library recovery replica quorum v0.

Derives a canonical durable checkpoint from several independently stored recovery
journals. Replica agreement is explicit, quorum-bound and fail-closed. Divergent
histories at the same or later sequence are treated as split-brain and never
silently merged. This module grants no runtime authority and performs no I/O.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .library_recovery_journal_v0 import RecoveryJournalV0, RecoveryJournalError, classify_recovery_resume_v0
from .library_recovery_transaction_v0 import RecoveryTransactionV0

_CTX=b"koschei.library-recovery-replica-quorum/v0\x00"

class RecoveryReplicaQuorumError(ValueError): pass

@dataclass(frozen=True,slots=True)
class RecoveryJournalReplicaV0:
    replica_id:str
    journal:RecoveryJournalV0
    storage_evidence_digest:bytes
    durable:bool=True
    authority:bool=False

@dataclass(frozen=True,slots=True)
class RecoveryCheckpointV0:
    graph_digest:bytes
    recovery_plan_digest:bytes
    preparation_digest:bytes
    canonical_journal_digest:bytes
    canonical_sequence:int
    agreeing_replica_ids:tuple[str,...]
    divergent_replica_ids:tuple[str,...]
    quorum_threshold:int
    checkpoint_digest:bytes
    durable:bool
    split_brain:bool
    authority:bool=False


def _d32(v:bytes,name:str)->bytes:
    if not isinstance(v,bytes) or len(v)!=32:
        raise RecoveryReplicaQuorumError(f"{name} must be exactly 32 bytes")
    return v


def _validate_replica(replica:RecoveryJournalReplicaV0,transaction:RecoveryTransactionV0)->tuple[int,bytes]:
    if not isinstance(replica,RecoveryJournalReplicaV0) or replica.authority:
        raise RecoveryReplicaQuorumError("authority-free recovery journal replica required")
    if not replica.replica_id or len(replica.replica_id)>96:
        raise RecoveryReplicaQuorumError("invalid replica identity")
    if not isinstance(replica.durable,bool):
        raise RecoveryReplicaQuorumError("replica durability flag must be boolean")
    ev=_d32(replica.storage_evidence_digest,"storage_evidence_digest")
    if ev==b"\x00"*32:
        raise RecoveryReplicaQuorumError("storage evidence cannot be empty")
    try:
        classify_recovery_resume_v0(journal=replica.journal,transaction=transaction)
    except RecoveryJournalError as exc:
        raise RecoveryReplicaQuorumError("replica journal verification failed") from exc
    if not replica.journal.entries:
        raise RecoveryReplicaQuorumError("replica journal cannot be empty")
    return len(replica.journal.entries),replica.journal.journal_digest


def derive_recovery_checkpoint_v0(*,transaction:RecoveryTransactionV0,replicas:tuple[RecoveryJournalReplicaV0,...],quorum_threshold:int)->RecoveryCheckpointV0:
    if not isinstance(transaction,RecoveryTransactionV0) or transaction.authority:
        raise RecoveryReplicaQuorumError("authority-free recovery transaction required")
    if not isinstance(replicas,tuple) or not replicas:
        raise RecoveryReplicaQuorumError("non-empty immutable replica tuple required")
    if not isinstance(quorum_threshold,int) or quorum_threshold<1 or quorum_threshold>len(replicas):
        raise RecoveryReplicaQuorumError("quorum threshold outside replica bounds")

    ids=set(); snapshots=[]
    for r in replicas:
        if r.replica_id in ids:
            raise RecoveryReplicaQuorumError("duplicate replica identity forbidden")
        ids.add(r.replica_id)
        seq,digest=_validate_replica(r,transaction)
        snapshots.append((r,seq,digest))

    # Group durable replicas by exact journal state. Only exact agreement can form
    # a checkpoint; histories are never merged or majority-voted entry-by-entry.
    groups={}
    for r,seq,digest in snapshots:
        if not r.durable:
            continue
        key=(seq,digest)
        groups.setdefault(key,[]).append(r)

    candidates=[]
    for (seq,digest),members in groups.items():
        if len(members)>=quorum_threshold:
            candidates.append((seq,digest,tuple(sorted(x.replica_id for x in members))))
    if not candidates:
        raise RecoveryReplicaQuorumError("no durable journal state satisfies quorum")

    # Prefer the greatest sequence only when exactly one quorum state exists at
    # that sequence. Two different quorum digests at the same max sequence are a
    # true split-brain and must not be auto-resolved.
    max_seq=max(x[0] for x in candidates)
    max_candidates=[x for x in candidates if x[0]==max_seq]
    split_brain=len({x[1] for x in max_candidates})>1
    if split_brain:
        raise RecoveryReplicaQuorumError("split-brain: competing quorum journal histories")
    seq,canonical_digest,agreeing=max_candidates[0]

    # A durable replica ahead of the selected checkpoint with a different digest
    # means the quorum view is stale or forked. Fail closed rather than rollback.
    for r,rseq,rdigest in snapshots:
        if r.durable and rseq>seq:
            raise RecoveryReplicaQuorumError("durable replica ahead of quorum checkpoint")
        if r.durable and rseq==seq and rdigest!=canonical_digest:
            # This is not a quorum split-brain by itself, but it is a divergent
            # durable peer and must be surfaced in the checkpoint evidence.
            pass

    divergent=tuple(sorted(r.replica_id for r,rseq,rdigest in snapshots if rseq!=seq or rdigest!=canonical_digest))
    h=hashlib.sha3_256(
        _CTX+b"checkpoint\x00"+transaction.graph_digest+transaction.recovery_plan_digest
        +transaction.preparation_digest+canonical_digest+seq.to_bytes(8,"big")
        +quorum_threshold.to_bytes(4,"big")
    )
    for rid in agreeing: h.update(b"A\x00"+rid.encode()+b"\x00")
    for rid in divergent: h.update(b"D\x00"+rid.encode()+b"\x00")
    for r,_,_ in sorted(snapshots,key=lambda x:x[0].replica_id):
        h.update(b"R\x00"+r.replica_id.encode()+b"\x00"+r.storage_evidence_digest+(b"\x01" if r.durable else b"\x00"))
    return RecoveryCheckpointV0(
        transaction.graph_digest,transaction.recovery_plan_digest,transaction.preparation_digest,
        canonical_digest,seq,agreeing,divergent,quorum_threshold,h.digest(),True,False,False
    )


def verify_recovery_checkpoint_v0(*,checkpoint:RecoveryCheckpointV0,transaction:RecoveryTransactionV0,replicas:tuple[RecoveryJournalReplicaV0,...])->bool:
    if not isinstance(checkpoint,RecoveryCheckpointV0) or checkpoint.authority or not checkpoint.durable or checkpoint.split_brain:
        return False
    try:
        rebuilt=derive_recovery_checkpoint_v0(transaction=transaction,replicas=replicas,quorum_threshold=checkpoint.quorum_threshold)
    except RecoveryReplicaQuorumError:
        return False
    return rebuilt==checkpoint
