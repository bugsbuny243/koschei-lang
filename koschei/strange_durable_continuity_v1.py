"""Local durable Continuity clock-window journal for Strange representation v1.

SQLite serializes admissions of epoch transitions on ONE database file. It
cannot prove independent clock authority, protect against privileged database
rollback, create hardware roots, or coordinate unrelated replica databases.

The journal stores NO source code, secret seeds, signing keys or Galaxy authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Callable

from .continuity_epoch_authority_v1 import (
    ContinuityEpochAuthorityV1,
    bind_continuity_epoch_authority_v1,
)

_WINDOW_SECONDS = 120
_MAX_INTEGER = 2**63 - 1


class StrangeDurableContinuityError(ValueError):
    """Missing, inconsistent, or non-monotonic durable Continuity state."""


@dataclass(frozen=True, slots=True)
class StrangeDurableObservationClaimV1:
    """Local replay tombstone; NOT a credential, token or execution approval."""

    continuity_id: str
    request_digest: str
    attestation_digest: str
    epoch: int
    observed_seconds: int
    authority: bool = False
    version: int = 1


@dataclass(frozen=True, slots=True)
class StrangeDurableEpochSnapshotV1:
    continuity_id: str
    epoch: int
    starts_at_seconds: int
    expires_before_seconds: int
    authority: bool = False
    version: int = 1


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise StrangeDurableContinuityError("nonempty bounded continuity identity required")
    return value


def _integer(value: int, field: str, *, zero_allowed: bool = False) -> int:
    low = 0 if zero_allowed else 1
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= _MAX_INTEGER:
        raise StrangeDurableContinuityError(f"invalid {field}")
    return value


def _hex_digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StrangeDurableContinuityError(f"invalid {label}")
    return value


def _trusted_seconds(reader: Callable[[], int]) -> int:
    if not callable(reader):
        raise StrangeDurableContinuityError("trusted seconds reader required")
    try:
        value = reader()
    except Exception as exc:
        raise StrangeDurableContinuityError("trusted clock read failed closed") from exc
    return _integer(value, "trusted seconds", zero_allowed=True)


def _window(epoch: int, start: int, observed: int) -> None:
    _integer(epoch, "epoch")
    _integer(start, "window start", zero_allowed=True)
    _integer(observed, "trusted observation", zero_allowed=True)
    if start > _MAX_INTEGER - _WINDOW_SECONDS:
        raise StrangeDurableContinuityError("window start exceeds durable clock range")
    if not start <= observed < start + _WINDOW_SECONDS:
        raise StrangeDurableContinuityError("observed time is outside requested epoch window")


class StrangeDurableContinuityV1:
    """Single-file transactional compare-and-swap epoch state.

    Callers must protect the database path, control who can publish transitions
    and supply timestamps from a separately trusted, monotonic clock. This is
    a local durability prototype, NOT independent identity or clock attestation.
    """

    def __init__(self, path: str | Path, *, continuity_id: str) -> None:
        self.continuity_id = _identifier(continuity_id)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False, timeout=20.0
        )
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=20000")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS strange_continuity_v1 (
                continuity_id TEXT PRIMARY KEY,
                epoch INTEGER NOT NULL CHECK(epoch > 0),
                starts_at_seconds INTEGER NOT NULL CHECK(starts_at_seconds >= 0)
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS strange_observation_claims_v1 (
                continuity_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                attestation_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch > 0),
                observed_seconds INTEGER NOT NULL CHECK(observed_seconds >= 0),
                PRIMARY KEY (continuity_id, request_digest)
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "StrangeDurableContinuityV1":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _snapshot(self, row: tuple[str, int, int] | None) -> StrangeDurableEpochSnapshotV1:
        if row is None or row[0] != self.continuity_id:
            raise StrangeDurableContinuityError("no admitted Continuity state")
        _integer(row[1], "stored epoch")
        _integer(row[2], "stored start", zero_allowed=True)
        if row[2] > _MAX_INTEGER - _WINDOW_SECONDS:
            raise StrangeDurableContinuityError("stored window is invalid")
        return StrangeDurableEpochSnapshotV1(
            continuity_id=row[0],
            epoch=row[1],
            starts_at_seconds=row[2],
            expires_before_seconds=row[2] + _WINDOW_SECONDS,
        )

    def read_snapshot(self) -> StrangeDurableEpochSnapshotV1:
        with self._lock:
            row = self._db.execute(
                "SELECT continuity_id,epoch,starts_at_seconds "
                "FROM strange_continuity_v1 WHERE continuity_id=?",
                (self.continuity_id,),
            ).fetchone()
        return self._snapshot(row)

    def initialize(
        self, *, epoch: int, starts_at_seconds: int, observed_seconds: int
    ) -> StrangeDurableEpochSnapshotV1:
        """Admit exactly one initial window; repeated initialization is denied."""
        _window(epoch, starts_at_seconds, observed_seconds)
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO strange_continuity_v1 "
                    "(continuity_id,epoch,starts_at_seconds) VALUES (?,?,?)",
                    (self.continuity_id, epoch, starts_at_seconds),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise StrangeDurableContinuityError(
                    "Continuity already initialized; never reinitialize an old epoch"
                ) from exc
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return StrangeDurableEpochSnapshotV1(
            continuity_id=self.continuity_id,
            epoch=epoch,
            starts_at_seconds=starts_at_seconds,
            expires_before_seconds=starts_at_seconds + _WINDOW_SECONDS,
        )

    def advance(
        self,
        *,
        expected_current_epoch: int,
        next_epoch: int,
        starts_at_seconds: int,
        observed_seconds: int,
    ) -> StrangeDurableEpochSnapshotV1:
        """CAS publish a strictly later 120-second slot, including skipped slots.

        A restart may skip elapsed windows, but cannot rewind a known epoch,
        claim an earlier window, or publish a fresh epoch under a stale CAS.
        """
        _integer(expected_current_epoch, "expected current epoch")
        _window(next_epoch, starts_at_seconds, observed_seconds)
        if next_epoch <= expected_current_epoch:
            raise StrangeDurableContinuityError("new epoch must be strictly later")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT continuity_id,epoch,starts_at_seconds "
                    "FROM strange_continuity_v1 WHERE continuity_id=?",
                    (self.continuity_id,),
                ).fetchone()
                old = self._snapshot(row)
                if old.epoch != expected_current_epoch:
                    raise StrangeDurableContinuityError(
                        "stale or conflicting Continuity compare-and-swap"
                    )
                expected_start = old.starts_at_seconds + (
                    next_epoch - old.epoch
                ) * _WINDOW_SECONDS
                if starts_at_seconds != expected_start:
                    raise StrangeDurableContinuityError(
                        "new epoch start must follow the exact fixed 120-second schedule"
                    )
                self._db.execute(
                    "UPDATE strange_continuity_v1 "
                    "SET epoch=?,starts_at_seconds=? WHERE continuity_id=?",
                    (next_epoch, starts_at_seconds, self.continuity_id),
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return StrangeDurableEpochSnapshotV1(
            continuity_id=self.continuity_id,
            epoch=next_epoch,
            starts_at_seconds=starts_at_seconds,
            expires_before_seconds=starts_at_seconds + _WINDOW_SECONDS,
        )

    def require_active_window(
        self,
        *,
        expected_epoch: int,
        expected_start_seconds: int,
        observed_seconds: int,
    ) -> StrangeDurableEpochSnapshotV1:
        """Verify the exact stored epoch AND its start, not just a caller epoch.

        Snapshot admission is not an atomic permission to perform a later
        critical effect. A separate isolated gate must re-verify Continuity
        and consume the exact execution authorization immediately at use time.
        """
        _window(expected_epoch, expected_start_seconds, observed_seconds)
        snapshot = self.read_snapshot()
        if (
            snapshot.epoch != expected_epoch
            or snapshot.starts_at_seconds != expected_start_seconds
        ):
            raise StrangeDurableContinuityError(
                "requested epoch/window differs from durable Continuity"
            )
        return snapshot

    def claim_observation_once(
        self,
        *,
        request_digest: str,
        attestation_digest: str,
        expected_epoch: int,
        expected_start_seconds: int,
        seconds_reader: Callable[[], int],
    ) -> StrangeDurableObservationClaimV1:
        """Atomically fence a non-authoritative local observation request.

        The active epoch and its EXACT canonical start are checked inside the
        same SQLite write transaction that inserts a permanent replay tombstone.
        The trusted time reader is called while the transaction is held so an
        old time captured before a contended lock cannot authorize the claim.
        This does not authorize the *underlying effect* or synchronize it with
        a remote signer. Never treat a claim as a transferable credential.
        """
        request = _hex_digest(request_digest, "request digest")
        attestation = _hex_digest(attestation_digest, "attestation digest")
        _integer(expected_epoch, "expected epoch")
        _integer(expected_start_seconds, "expected start", zero_allowed=True)
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT continuity_id,epoch,starts_at_seconds "
                    "FROM strange_continuity_v1 WHERE continuity_id=?",
                    (self.continuity_id,),
                ).fetchone()
                snapshot = self._snapshot(row)
                if (
                    snapshot.epoch != expected_epoch
                    or snapshot.starts_at_seconds != expected_start_seconds
                ):
                    raise StrangeDurableContinuityError(
                        "observation request uses stale or substituted Continuity"
                    )
                now = _trusted_seconds(seconds_reader)
                _window(expected_epoch, expected_start_seconds, now)
                self._db.execute(
                    "INSERT INTO strange_observation_claims_v1 "
                    "(continuity_id,request_digest,attestation_digest,epoch,observed_seconds) "
                    "VALUES (?,?,?,?,?)",
                    (self.continuity_id, request, attestation, expected_epoch, now),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise StrangeDurableContinuityError(
                    "observation request already claimed; replay denied"
                ) from exc
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return StrangeDurableObservationClaimV1(
            continuity_id=self.continuity_id,
            request_digest=request,
            attestation_digest=attestation,
            epoch=expected_epoch,
            observed_seconds=now,
        )

    def as_continuity_authority(self) -> ContinuityEpochAuthorityV1:
        """Bind the existing typed epoch reader; grants NO effect authority."""
        return bind_continuity_epoch_authority_v1(
            continuity_id=self.continuity_id,
            epoch_reader=lambda: self.read_snapshot().epoch,
        )
