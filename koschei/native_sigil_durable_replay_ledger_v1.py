"""Durable replay ledger for native Koschei privileged effects v1.

This module upgrades the in-memory ReplayLedger contract to a durable SQLite
backend with transactional uniqueness. A request digest can be claimed only
once, survives process restart, and remains fail-closed after crashes.

A CLAIMED row discovered after restart is treated as unresolved in-flight work.
It is not automatically retried. Callers must resolve it explicitly to a
terminal state after checking external effect finality.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import RLock

from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_replay_ledger_v1 import (
    NativeSigilReplayError,
    ReplayRecord,
    _record_digest,
)
from .native_sigil_request_binding_v1 import CanonicalEffectRequest


_TERMINAL_STATES = {"COMMITTED", "REJECTED", "CONTAINED", "UNCERTAIN"}


class DurableReplayLedger:
    """Transactional replay ledger backed by one local SQLite database.

    SQLite provides durable uniqueness for request digests and atomic state
    transitions on one database file. This class does not claim distributed
    consensus across independent database replicas.
    """

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
            CREATE TABLE IF NOT EXISTS replay_records (
                request_digest TEXT PRIMARY KEY,
                effect_id TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 0),
                state TEXT NOT NULL,
                proof_digest TEXT NOT NULL,
                decision_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableReplayLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _row_to_record(self, row: tuple[str, str, int, str, str, str, str]) -> ReplayRecord:
        record = ReplayRecord(
            request_digest=row[0],
            effect_id=row[1],
            epoch=row[2],
            state=row[3],
            proof_digest=row[4],
            decision_digest=row[5],
            digest=row[6],
        )
        expected = _record_digest(
            record.request_digest,
            record.effect_id,
            record.epoch,
            record.state,
            record.proof_digest,
            record.decision_digest,
        )
        if expected != record.digest:
            raise NativeSigilReplayError("durable replay record integrity mismatch")
        return record

    def get(self, request_digest: str) -> ReplayRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT request_digest,effect_id,epoch,state,proof_digest,decision_digest,record_digest "
                "FROM replay_records WHERE request_digest=?",
                (request_digest,),
            ).fetchone()
            return None if row is None else self._row_to_record(row)

    def claim(self, request: CanonicalEffectRequest, proof_digest: str) -> ReplayRecord:
        record = ReplayRecord(
            request_digest=request.digest,
            effect_id=request.effect_id,
            epoch=request.epoch,
            state="CLAIMED",
            proof_digest=proof_digest,
            decision_digest="pending",
            digest=_record_digest(
                request.digest,
                request.effect_id,
                request.epoch,
                "CLAIMED",
                proof_digest,
                "pending",
            ),
        )
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO replay_records "
                    "(request_digest,effect_id,epoch,state,proof_digest,decision_digest,record_digest) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        record.request_digest,
                        record.effect_id,
                        record.epoch,
                        record.state,
                        record.proof_digest,
                        record.decision_digest,
                        record.digest,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                existing = self.get(request.digest)
                state = "UNKNOWN" if existing is None else existing.state
                raise NativeSigilReplayError(
                    f"privileged request already consumed or in-flight: {state}"
                ) from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return record

    def finalize(
        self,
        request: CanonicalEffectRequest,
        proof_digest: str,
        decision: EnforcementDecision,
        *,
        state: str,
    ) -> ReplayRecord:
        if state not in _TERMINAL_STATES:
            raise NativeSigilReplayError(f"invalid replay final state: {state}")
        record = ReplayRecord(
            request_digest=request.digest,
            effect_id=request.effect_id,
            epoch=request.epoch,
            state=state,
            proof_digest=proof_digest,
            decision_digest=decision.digest,
            digest=_record_digest(
                request.digest,
                request.effect_id,
                request.epoch,
                state,
                proof_digest,
                decision.digest,
            ),
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            current = self._db.execute(
                "SELECT state,proof_digest FROM replay_records WHERE request_digest=?",
                (request.digest,),
            ).fetchone()
            if current is None or current[0] != "CLAIMED":
                self._db.execute("ROLLBACK")
                raise NativeSigilReplayError("request was not durably claimed")
            if current[1] != proof_digest:
                self._db.execute("ROLLBACK")
                raise NativeSigilReplayError("claimed proof digest changed before finality")
            self._db.execute(
                "UPDATE replay_records SET state=?,decision_digest=?,record_digest=? "
                "WHERE request_digest=? AND state='CLAIMED'",
                (state, decision.digest, record.digest, request.digest),
            )
            self._db.execute("COMMIT")
        return record

    def unresolved_claims(self) -> tuple[ReplayRecord, ...]:
        """Return crash-surviving CLAIMED records requiring explicit resolution."""
        with self._lock:
            rows = self._db.execute(
                "SELECT request_digest,effect_id,epoch,state,proof_digest,decision_digest,record_digest "
                "FROM replay_records WHERE state='CLAIMED' ORDER BY request_digest"
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)

    def resolve_uncertain_after_recovery(
        self,
        request: CanonicalEffectRequest,
        proof_digest: str,
        decision: EnforcementDecision,
    ) -> ReplayRecord:
        """Tombstone an unresolved crashed claim after external finality remains unknown."""
        return self.finalize(
            request,
            proof_digest,
            decision,
            state="UNCERTAIN",
        )
