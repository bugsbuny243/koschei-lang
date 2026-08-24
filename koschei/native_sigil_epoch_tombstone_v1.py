"""Durable epoch tombstones for native Koschei privileged execution v1.

Request binding prevents a proof from moving between requests, and replay ledgers
prevent one exact request from being consumed twice. Neither rule is sufficient
after Universe containment/rebirth: a completely new nonce in an obsolete epoch
must still be rejected.

This module makes epoch closure durable. A rebirth receipt advances one activation-
plan identity from N to N+1 and tombstones N. Privileged requests are accepted
only for the exact current activation epoch of their Universe plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3
from threading import RLock

from .native_sigil_request_binding_v1 import CanonicalEffectRequest
from .universe_rebirth_v1 import RebirthReceipt, require_rebirth_receipt
from .universe_state_machine_v1 import UniverseState

_CTX = b"koschei.native-sigil-epoch-tombstone/v1\x00"


class EpochTombstoneError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EpochRecord:
    activation_plan_digest: str
    current_epoch: int
    previous_epoch: int | None
    cause_digest: str
    record_digest: str


def _digest(plan: str, current: int, previous: int | None, cause: str) -> str:
    payload = "\n".join(
        (
            f"plan={plan}",
            f"current={current}",
            f"previous={'' if previous is None else previous}",
            f"cause={cause}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def _request_activation_plan(request: CanonicalEffectRequest) -> str:
    plan = getattr(request, "activation_plan_digest", "")
    if not plan:
        raise EpochTombstoneError("request is not bound to an activation-plan identity")
    return plan


class DurableEpochFence:
    """Durable single-database epoch authority for one or more activation plans."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS epoch_heads (
                activation_plan_digest TEXT PRIMARY KEY,
                current_epoch INTEGER NOT NULL CHECK(current_epoch >= 1),
                previous_epoch INTEGER,
                cause_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS epoch_tombstones (
                activation_plan_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 1),
                cause_digest TEXT NOT NULL,
                PRIMARY KEY (activation_plan_digest, epoch)
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableEpochFence":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def initialize(self, state: UniverseState, *, cause_digest: str = "genesis") -> EpochRecord:
        epochs = {row.epoch for row in state.sigils}
        if len(epochs) != 1:
            raise EpochTombstoneError("cannot initialize epoch fence from split-epoch state")
        epoch = next(iter(epochs))
        record_digest = _digest(state.activation_plan_digest, epoch, None, cause_digest)
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO epoch_heads VALUES (?,?,?,?,?)",
                    (state.activation_plan_digest, epoch, None, cause_digest, record_digest),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise EpochTombstoneError("epoch fence already initialized for Universe plan") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return EpochRecord(state.activation_plan_digest, epoch, None, cause_digest, record_digest)

    def current(self, plan_digest: str) -> EpochRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT activation_plan_digest,current_epoch,previous_epoch,cause_digest,record_digest "
                "FROM epoch_heads WHERE activation_plan_digest=?",
                (plan_digest,),
            ).fetchone()
        if row is None:
            return None
        record = EpochRecord(*row)
        expected = _digest(record.activation_plan_digest, record.current_epoch, record.previous_epoch, record.cause_digest)
        if expected != record.record_digest:
            raise EpochTombstoneError("durable epoch-head integrity mismatch")
        return record

    def advance_rebirth(
        self,
        previous: UniverseState,
        fresh: UniverseState,
        receipt: RebirthReceipt,
    ) -> EpochRecord:
        require_rebirth_receipt(previous, fresh, receipt)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            head = self._db.execute(
                "SELECT current_epoch FROM epoch_heads WHERE activation_plan_digest=?",
                (receipt.activation_plan_digest,),
            ).fetchone()
            if head is None:
                self._db.execute("ROLLBACK")
                raise EpochTombstoneError("epoch fence is not initialized for Universe plan")
            if head[0] != receipt.previous_epoch:
                self._db.execute("ROLLBACK")
                raise EpochTombstoneError("rebirth does not advance the current durable epoch")
            self._db.execute(
                "INSERT INTO epoch_tombstones VALUES (?,?,?)",
                (receipt.activation_plan_digest, receipt.previous_epoch, receipt.digest),
            )
            record_digest = _digest(
                receipt.activation_plan_digest,
                receipt.next_epoch,
                receipt.previous_epoch,
                receipt.digest,
            )
            changed = self._db.execute(
                "UPDATE epoch_heads SET current_epoch=?,previous_epoch=?,cause_digest=?,record_digest=? "
                "WHERE activation_plan_digest=? AND current_epoch=?",
                (
                    receipt.next_epoch,
                    receipt.previous_epoch,
                    receipt.digest,
                    record_digest,
                    receipt.activation_plan_digest,
                    receipt.previous_epoch,
                ),
            ).rowcount
            if changed != 1:
                self._db.execute("ROLLBACK")
                raise EpochTombstoneError("concurrent or non-monotonic epoch advance rejected")
            self._db.execute("COMMIT")
        return EpochRecord(
            receipt.activation_plan_digest,
            receipt.next_epoch,
            receipt.previous_epoch,
            receipt.digest,
            record_digest,
        )

    def is_tombstoned(self, plan_digest: str, epoch: int) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM epoch_tombstones WHERE activation_plan_digest=? AND epoch=?",
                (plan_digest, epoch),
            ).fetchone()
            return row is not None

    def require_current_request(self, request: CanonicalEffectRequest) -> None:
        plan = _request_activation_plan(request)
        head = self.current(plan)
        if head is None:
            raise EpochTombstoneError("no durable epoch authority for request activation plan")
        if self.is_tombstoned(plan, request.epoch):
            raise EpochTombstoneError("request belongs to a tombstoned Universe epoch")
        if request.epoch != head.current_epoch:
            raise EpochTombstoneError(
                f"request epoch is not current: request={request.epoch} current={head.current_epoch}"
            )
