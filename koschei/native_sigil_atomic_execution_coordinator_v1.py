"""Atomic durable execution coordinator for native Koschei privileged effects v1.

This is the production-oriented bridge between Universe epoch safety and replay
safety. Earlier reference modules intentionally kept the durable epoch fence and
durable replay ledger separate. A privileged boundary must not leave a race
between "epoch is current" and "request is claimed". This coordinator performs
both checks and the request claim in one SQLite BEGIN IMMEDIATE transaction.

It also binds Nuclear Containment to the durable execution boundary. Once a
verified nuclear-containment receipt is applied, the current epoch is tombstoned
and the Universe plan is frozen atomically. New requests for that epoch cannot
enter even with a fresh nonce or previously unseen request digest.

No offensive/external action exists here; all operations are local fail-closed
state transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3
from threading import RLock

from .native_sigil_request_binding_v1 import CanonicalEffectRequest
from .universe_nuclear_containment_v1 import (
    NuclearContainmentReceipt,
    require_nuclear_containment,
)
from .universe_rebirth_v1 import RebirthReceipt, require_rebirth_receipt
from .universe_state_machine_v1 import UniverseState

_CTX = b"koschei.native-sigil-atomic-execution-coordinator/v1\x00"


class AtomicExecutionCoordinatorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AtomicClaim:
    request_digest: str
    activation_plan_digest: str
    epoch: int
    proof_digest: str
    state: str
    digest: str


@dataclass(frozen=True, slots=True)
class ExecutionEpochHead:
    activation_plan_digest: str
    current_epoch: int
    frozen: bool
    cause_digest: str
    digest: str


def _head_digest(plan: str, epoch: int, frozen: bool, cause: str) -> str:
    payload = "\n".join((plan, str(epoch), str(int(frozen)), cause)).encode("utf-8")
    return hashlib.sha256(_CTX + b"head\x00" + payload).hexdigest()


def _claim_digest(request: str, plan: str, epoch: int, proof: str, state: str) -> str:
    payload = "\n".join((request, plan, str(epoch), proof, state)).encode("utf-8")
    return hashlib.sha256(_CTX + b"claim\x00" + payload).hexdigest()


def _request_activation_plan(request: CanonicalEffectRequest) -> str:
    plan = getattr(request, "activation_plan_digest", "")
    if plan:
        return plan
    # Compatibility for the narrow test/request stubs that predate canonical
    # activation-plan binding and already carry an activation-plan digest in the
    # historical field name.
    plan = getattr(request, "universe_plan_digest", "")
    if not plan:
        raise AtomicExecutionCoordinatorError("request has no activation-plan identity")
    return plan


class AtomicExecutionCoordinator:
    """One durable authority for epoch validity plus exact-request consumption."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_epoch_heads (
                activation_plan_digest TEXT PRIMARY KEY,
                current_epoch INTEGER NOT NULL CHECK(current_epoch >= 1),
                frozen INTEGER NOT NULL CHECK(frozen IN (0,1)),
                cause_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_epoch_tombstones (
                activation_plan_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 1),
                cause_digest TEXT NOT NULL,
                PRIMARY KEY (activation_plan_digest, epoch)
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_claims (
                request_digest TEXT PRIMARY KEY,
                activation_plan_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 1),
                proof_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "AtomicExecutionCoordinator":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def initialize(self, state: UniverseState, *, cause_digest: str = "genesis") -> ExecutionEpochHead:
        epochs = {row.epoch for row in state.sigils}
        if len(epochs) != 1:
            raise AtomicExecutionCoordinatorError("split-epoch Universe cannot initialize execution coordinator")
        epoch = next(iter(epochs))
        digest = _head_digest(state.activation_plan_digest, epoch, False, cause_digest)
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO execution_epoch_heads VALUES (?,?,?,?,?)",
                    (state.activation_plan_digest, epoch, 0, cause_digest, digest),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise AtomicExecutionCoordinatorError("execution coordinator already initialized") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return ExecutionEpochHead(state.activation_plan_digest, epoch, False, cause_digest, digest)

    def current(self, plan_digest: str) -> ExecutionEpochHead | None:
        with self._lock:
            row = self._db.execute(
                "SELECT activation_plan_digest,current_epoch,frozen,cause_digest,record_digest "
                "FROM execution_epoch_heads WHERE activation_plan_digest=?",
                (plan_digest,),
            ).fetchone()
        if row is None:
            return None
        head = ExecutionEpochHead(row[0], row[1], bool(row[2]), row[3], row[4])
        if head.digest != _head_digest(head.activation_plan_digest, head.current_epoch, head.frozen, head.cause_digest):
            raise AtomicExecutionCoordinatorError("execution epoch-head integrity mismatch")
        return head

    def atomic_claim(self, request: CanonicalEffectRequest, proof_digest: str) -> AtomicClaim:
        """Check current epoch/freeze/tombstone and claim the request atomically."""
        if not proof_digest:
            raise AtomicExecutionCoordinatorError("atomic claim requires proof digest")
        plan = _request_activation_plan(request)
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                head = self._db.execute(
                    "SELECT current_epoch,frozen FROM execution_epoch_heads WHERE activation_plan_digest=?",
                    (plan,),
                ).fetchone()
                if head is None:
                    raise AtomicExecutionCoordinatorError("no durable execution authority for request Universe")
                if bool(head[1]):
                    raise AtomicExecutionCoordinatorError("Universe execution boundary is frozen")
                if request.epoch != head[0]:
                    raise AtomicExecutionCoordinatorError(
                        f"request epoch is not current: request={request.epoch} current={head[0]}"
                    )
                tombstone = self._db.execute(
                    "SELECT 1 FROM execution_epoch_tombstones WHERE activation_plan_digest=? AND epoch=?",
                    (plan, request.epoch),
                ).fetchone()
                if tombstone is not None:
                    raise AtomicExecutionCoordinatorError("request belongs to a tombstoned epoch")
                digest = _claim_digest(
                    request.digest,
                    plan,
                    request.epoch,
                    proof_digest,
                    "CLAIMED",
                )
                self._db.execute(
                    "INSERT INTO execution_claims VALUES (?,?,?,?,?,?)",
                    (
                        request.digest,
                        plan,
                        request.epoch,
                        proof_digest,
                        "CLAIMED",
                        digest,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise AtomicExecutionCoordinatorError("privileged request already claimed or consumed") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return AtomicClaim(
            request.digest,
            plan,
            request.epoch,
            proof_digest,
            "CLAIMED",
            digest,
        )

    def finalize_claim(self, claim: AtomicClaim, *, state: str, decision_digest: str) -> AtomicClaim:
        if state not in {"COMMITTED", "REJECTED", "CONTAINED", "UNCERTAIN"}:
            raise AtomicExecutionCoordinatorError(f"invalid claim final state: {state}")
        if not decision_digest:
            raise AtomicExecutionCoordinatorError("claim finality requires decision digest")
        terminal_proof = hashlib.sha256(
            _CTX + b"finality\x00" + (claim.proof_digest + "\n" + decision_digest).encode("utf-8")
        ).hexdigest()
        digest = _claim_digest(
            claim.request_digest,
            claim.activation_plan_digest,
            claim.epoch,
            terminal_proof,
            state,
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute(
                "SELECT state,proof_digest FROM execution_claims WHERE request_digest=?",
                (claim.request_digest,),
            ).fetchone()
            if row is None or row[0] != "CLAIMED" or row[1] != claim.proof_digest:
                self._db.execute("ROLLBACK")
                raise AtomicExecutionCoordinatorError("claim is missing, changed, or already finalized")
            self._db.execute(
                "UPDATE execution_claims SET proof_digest=?,state=?,record_digest=? WHERE request_digest=? AND state='CLAIMED'",
                (terminal_proof, state, digest, claim.request_digest),
            )
            self._db.execute("COMMIT")
        return AtomicClaim(
            claim.request_digest,
            claim.activation_plan_digest,
            claim.epoch,
            terminal_proof,
            state,
            digest,
        )

    def apply_nuclear_containment(
        self,
        previous: UniverseState,
        contained: UniverseState,
        receipt: NuclearContainmentReceipt,
    ) -> ExecutionEpochHead:
        """Atomically freeze the Universe plan and tombstone its current epoch."""
        require_nuclear_containment(previous, contained, receipt)
        plan = previous.activation_plan_digest
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                head = self._db.execute(
                    "SELECT current_epoch,frozen FROM execution_epoch_heads WHERE activation_plan_digest=?",
                    (plan,),
                ).fetchone()
                if head is None:
                    raise AtomicExecutionCoordinatorError("execution coordinator is not initialized")
                if head[0] != receipt.epoch:
                    raise AtomicExecutionCoordinatorError("nuclear receipt does not match durable current epoch")
                if bool(head[1]):
                    raise AtomicExecutionCoordinatorError("Universe execution boundary is already frozen")
                self._db.execute(
                    "INSERT INTO execution_epoch_tombstones VALUES (?,?,?)",
                    (plan, receipt.epoch, receipt.digest),
                )
                digest = _head_digest(plan, receipt.epoch, True, receipt.digest)
                changed = self._db.execute(
                    "UPDATE execution_epoch_heads SET frozen=1,cause_digest=?,record_digest=? "
                    "WHERE activation_plan_digest=? AND current_epoch=? AND frozen=0",
                    (receipt.digest, digest, plan, receipt.epoch),
                ).rowcount
                if changed != 1:
                    raise AtomicExecutionCoordinatorError("concurrent nuclear containment rejected")
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return ExecutionEpochHead(plan, receipt.epoch, True, receipt.digest, digest)

    def advance_rebirth(
        self,
        previous: UniverseState,
        fresh: UniverseState,
        receipt: RebirthReceipt,
    ) -> ExecutionEpochHead:
        """Advance a frozen/tombstoned epoch only with a verified rebirth receipt."""
        require_rebirth_receipt(previous, fresh, receipt)
        plan = receipt.activation_plan_digest
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                head = self._db.execute(
                    "SELECT current_epoch,frozen FROM execution_epoch_heads WHERE activation_plan_digest=?",
                    (plan,),
                ).fetchone()
                if head is None:
                    raise AtomicExecutionCoordinatorError("execution coordinator is not initialized")
                if head[0] != receipt.previous_epoch or not bool(head[1]):
                    raise AtomicExecutionCoordinatorError("rebirth requires the frozen previous durable epoch")
                tombstone = self._db.execute(
                    "SELECT 1 FROM execution_epoch_tombstones WHERE activation_plan_digest=? AND epoch=?",
                    (plan, receipt.previous_epoch),
                ).fetchone()
                if tombstone is None:
                    raise AtomicExecutionCoordinatorError("rebirth requires previous epoch tombstone")
                digest = _head_digest(plan, receipt.next_epoch, False, receipt.digest)
                changed = self._db.execute(
                    "UPDATE execution_epoch_heads SET current_epoch=?,frozen=0,cause_digest=?,record_digest=? "
                    "WHERE activation_plan_digest=? AND current_epoch=? AND frozen=1",
                    (
                        receipt.next_epoch,
                        receipt.digest,
                        digest,
                        plan,
                        receipt.previous_epoch,
                    ),
                ).rowcount
                if changed != 1:
                    raise AtomicExecutionCoordinatorError("concurrent or non-monotonic rebirth rejected")
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return ExecutionEpochHead(plan, receipt.next_epoch, False, receipt.digest, digest)
