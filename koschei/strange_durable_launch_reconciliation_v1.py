"""Local crash-visible launch-attempt journal for Strange epoch handoff.

This module is intentionally outside privileged effect authorization. It
reserves at most ONE local launch attempt for an activated epoch, and records
only what an external operator/runner reports about the outcome. Failed,
abandoned, or unknown attempts NEVER roll the durable Continuity epoch back.

No atomic coupling to os.exec, process supervision or remote signing exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import sqlite3
from typing import Callable

from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
    _hex_digest,
    _integer,
    _trusted_seconds,
    _window,
)
from .strange_epoch_handoff_v1 import (
    StrangeEpochHandoffError,
    StrangeEpochHandoffV1,
    _mac as handoff_mac,
    _secret as handoff_key_check,
)


class StrangeLaunchReconciliationError(ValueError):
    """The local launch report cannot be durably reserved or reconciled."""


@dataclass(frozen=True, slots=True)
class StrangeLaunchAttemptV1:
    """Untrusted observation/report; NEVER use as a launch or signing ticket."""

    continuity_id: str
    epoch: int
    old_epoch: int
    handoff_mac: str
    native_sha256: str
    claimed_seconds: int
    state: str
    reported_seconds: int | None = None
    authority: bool = False
    version: int = 1


class StrangeDurableLaunchReconciliationV1:
    """One local SQLite launch-attempt record per continuity identity/epoch.

    Callers must restrict the DB path and protect the handoff key externally.
    The claim is not an OS lock or a distributed exactly-once execution gate.
    """

    def __init__(self, continuity_store: StrangeDurableContinuityV1) -> None:
        if not isinstance(continuity_store, StrangeDurableContinuityV1):
            raise StrangeLaunchReconciliationError("typed durable Continuity required")
        self.store = continuity_store
        self.handoff = StrangeEpochHandoffV1(continuity_store)
        with self.store._lock:
            self.store._db.execute(
                """CREATE TABLE IF NOT EXISTS strange_launch_attempts_v1 (
                    continuity_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL CHECK(epoch > 0),
                    old_epoch INTEGER NOT NULL CHECK(old_epoch > 0),
                    handoff_mac TEXT NOT NULL,
                    native_sha256 TEXT NOT NULL,
                    claimed_seconds INTEGER NOT NULL CHECK(claimed_seconds >= 0),
                    state TEXT NOT NULL CHECK(state IN
                        ('CLAIMED', 'REPORTED_OK', 'REPORTED_FAILED')),
                    reported_seconds INTEGER CHECK(reported_seconds >= 0),
                    PRIMARY KEY(continuity_id,epoch)
                )"""
            )

    def _read_locked(self, epoch: int) -> StrangeLaunchAttemptV1:
        row = self.store._db.execute(
            "SELECT continuity_id,epoch,old_epoch,handoff_mac,native_sha256,"
            "claimed_seconds,state,reported_seconds FROM strange_launch_attempts_v1 "
            "WHERE continuity_id=? AND epoch=?",
            (self.store.continuity_id, epoch),
        ).fetchone()
        if row is None:
            raise StrangeLaunchReconciliationError("launch attempt not recorded")
        item = StrangeLaunchAttemptV1(*row[:6], row[6], row[7])
        if item.continuity_id != self.store.continuity_id:
            raise StrangeLaunchReconciliationError("foreign Continuity attempt")
        return item

    def read(self, *, epoch: int) -> StrangeLaunchAttemptV1:
        _integer(epoch, "launch epoch")
        with self.store._lock:
            return self._read_locked(epoch)

    def claim_once(
        self,
        *,
        expected_epoch: int,
        expected_handoff_mac: str,
        expected_native_sha256: str,
        handoff_key: bytes,
        seconds_reader: Callable[[], int],
    ) -> StrangeLaunchAttemptV1:
        """Record one candidate launch attempt in the exact ACTIVE epoch.

        An operator should call this BEFORE launching a candidate, then record
        its result. A crash leaves CLAIMED, never an implicit permission to
        launch the same binary again. The Python entrypoint is bypassable.
        """
        _integer(expected_epoch, "launch epoch")
        if expected_epoch <= 1:
            raise StrangeLaunchReconciliationError("next-epoch handoff required")
        try:
            _hex_digest(expected_handoff_mac, "handoff MAC")
            _hex_digest(expected_native_sha256, "native SHA256")
            key = handoff_key_check(handoff_key)
        except (StrangeDurableContinuityError, StrangeEpochHandoffError) as exc:
            raise StrangeLaunchReconciliationError("invalid launch identity") from exc
        with self.store._lock:
            try:
                self.store._db.execute("BEGIN IMMEDIATE")
                snapshot = self.store._snapshot(self.store._db.execute(
                    "SELECT continuity_id,epoch,starts_at_seconds FROM strange_continuity_v1 "
                    "WHERE continuity_id=?", (self.store.continuity_id,),
                ).fetchone())
                stage = self.handoff._read(expected_epoch - 1)
                calculated = handoff_mac(key, stage)
                retired = self.store._db.execute(
                    "SELECT handoff_mac FROM strange_handoff_retired_v1 "
                    "WHERE continuity_id=? AND epoch=?",
                    (self.store.continuity_id, expected_epoch - 1),
                ).fetchone()
                if (
                    snapshot.epoch != expected_epoch
                    or snapshot.starts_at_seconds != stage.next_start_seconds
                    or stage.next_epoch != expected_epoch
                    or stage.state != "ACTIVATED"
                    or retired is None
                    or not hmac.compare_digest(retired[0], calculated)
                    or not hmac.compare_digest(stage.handoff_mac, calculated)
                    or not hmac.compare_digest(expected_handoff_mac, calculated)
                    or not hmac.compare_digest(expected_native_sha256, stage.native_sha256)
                ):
                    raise StrangeLaunchReconciliationError(
                        "unverified, stale or substituted activated candidate"
                    )
                now = _trusted_seconds(seconds_reader)
                _window(expected_epoch, stage.next_start_seconds, now)
                self.store._db.execute(
                    "INSERT INTO strange_launch_attempts_v1 "
                    "(continuity_id,epoch,old_epoch,handoff_mac,native_sha256,"
                    "claimed_seconds,state,reported_seconds) VALUES (?,?,?,?,?,?,?,NULL)",
                    (self.store.continuity_id, expected_epoch, expected_epoch - 1,
                     calculated, stage.native_sha256, now, "CLAIMED"),
                )
                self.store._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self.store._db.execute("ROLLBACK")
                raise StrangeLaunchReconciliationError(
                    "launch attempt already claimed; manual reconciliation required"
                ) from exc
            except Exception:
                self.store._db.execute("ROLLBACK")
                raise
        return StrangeLaunchAttemptV1(
            continuity_id=self.store.continuity_id, epoch=expected_epoch,
            old_epoch=expected_epoch - 1, handoff_mac=calculated,
            native_sha256=stage.native_sha256, claimed_seconds=now,
            state="CLAIMED",
        )

    def record_result(
        self,
        *,
        epoch: int,
        expected_handoff_mac: str,
        reported_success: bool,
        seconds_reader: Callable[[], int],
        handoff_key: bytes,
    ) -> StrangeLaunchAttemptV1:
        """Record external runner outcome ONCE; success is not verified proof.

        An unsuccessful report can be recorded even after the window expires.
        Positive reports require the epoch to STILL be current and unexpired;
        otherwise a stale process would be incorrectly recorded as current.
        """
        _integer(epoch, "launch epoch")
        if not isinstance(reported_success, bool):
            raise StrangeLaunchReconciliationError("boolean runner report required")
        try:
            _hex_digest(expected_handoff_mac, "handoff MAC")
            key = handoff_key_check(handoff_key)
        except (StrangeDurableContinuityError, StrangeEpochHandoffError) as exc:
            raise StrangeLaunchReconciliationError("invalid handoff report identity") from exc
        with self.store._lock:
            try:
                self.store._db.execute("BEGIN IMMEDIATE")
                claim = self._read_locked(epoch)
                if (
                    claim.state != "CLAIMED"
                    or not hmac.compare_digest(claim.handoff_mac, expected_handoff_mac)
                ):
                    raise StrangeLaunchReconciliationError(
                        "stale or already reconciled launch report"
                    )
                stage = self.handoff._read(claim.old_epoch)
                authenticated = handoff_mac(key, stage)
                if (
                    stage.state != "ACTIVATED"
                    or stage.next_epoch != epoch
                    or stage.native_sha256 != claim.native_sha256
                    or not hmac.compare_digest(authenticated, claim.handoff_mac)
                ):
                    raise StrangeLaunchReconciliationError(
                        "runner report is not bound to authenticated stage"
                    )
                now = _trusted_seconds(seconds_reader)
                if now < claim.claimed_seconds:
                    raise StrangeLaunchReconciliationError("launch report clock rolled back")
                if reported_success:
                    snapshot = self.store._snapshot(self.store._db.execute(
                        "SELECT continuity_id,epoch,starts_at_seconds "
                        "FROM strange_continuity_v1 WHERE continuity_id=?",
                        (self.store.continuity_id,),
                    ).fetchone())
                    if snapshot.epoch != epoch:
                        raise StrangeLaunchReconciliationError(
                            "success report arrived after epoch rotation"
                        )
                    _window(epoch, snapshot.starts_at_seconds, now)
                state = "REPORTED_OK" if reported_success else "REPORTED_FAILED"
                self.store._db.execute(
                    "UPDATE strange_launch_attempts_v1 SET state=?,reported_seconds=? "
                    "WHERE continuity_id=? AND epoch=? AND state='CLAIMED'",
                    (state, now, self.store.continuity_id, epoch),
                )
                self.store._db.execute("COMMIT")
            except Exception:
                self.store._db.execute("ROLLBACK")
                raise
        return StrangeLaunchAttemptV1(
            continuity_id=claim.continuity_id, epoch=claim.epoch,
            old_epoch=claim.old_epoch, handoff_mac=claim.handoff_mac,
            native_sha256=claim.native_sha256,
            claimed_seconds=claim.claimed_seconds,
            state=state, reported_seconds=now,
        )
