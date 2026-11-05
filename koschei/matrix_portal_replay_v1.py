"""Durable, single-ledger Matrix portal replay fence.

An approved application may consume an already authenticated and authorized
portal proof at most once in one SQLite ledger. This module verifies the full
portal integrity record and atomically records its digest via BEGIN IMMEDIATE.

IMPORTANT: the proof is a public checksum, NOT an issuer signature or an
authorization. Any caller able to invoke consume() can burn a proof (DoS).
Callers MUST authenticate current Reality state and approve the effect,
recipient and target *before* invoking consume(). This ledger never
executes an effect, and does not promise exactly-once external side effects.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from threading import RLock

from .matrix_portal_transit_v1 import (
    PortalTransitProofV1,
    portal_matches_reality_v1,
)
from .wanda_reality_integrity_v1 import RealityCommitmentV1


class PortalReplayFenceError(ValueError):
    """Invalid integrity evidence or an already consumed portal proof."""


class DurablePortalReplayFence:
    """A transactional at-most-once admission ledger for one SQLite database.

    Each process must use the SAME durable database for shared replay safety.
    WAL and BEGIN IMMEDIATE serialize competing writers across connections.
    Network filesystems, externally modified databases and ledger deletion are
    outside this guarantee. The digest alone is not authorization.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, timeout=10,
            check_same_thread=False,
        )
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS matrix_portal_consumed (
                transit_digest BLOB PRIMARY KEY NOT NULL
                    CHECK(length(transit_digest) = 32),
                source_reality TEXT NOT NULL,
                destination_reality TEXT NOT NULL,
                source_commitment BLOB NOT NULL,
                destination_commitment BLOB NOT NULL,
                payload_digest BLOB NOT NULL,
                effect TEXT NOT NULL,
                target_digest BLOB NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 0)
            ) WITHOUT ROWID
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurablePortalReplayFence":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def is_consumed(self, transit_digest: bytes) -> bool:
        """Read-only check; NEVER use the check alone as a race-free gate."""
        if not isinstance(transit_digest, bytes) or len(transit_digest) != 32:
            raise PortalReplayFenceError("transit digest must be 32 bytes")
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM matrix_portal_consumed WHERE transit_digest=?",
                (transit_digest,),
            ).fetchone()
        return row is not None

    def consume(
        self, proof: PortalTransitProofV1, *,
        source: RealityCommitmentV1,
        destination: RealityCommitmentV1,
        payload_digest: bytes,
        effect: str,
        target_digest: bytes,
        epoch: int,
    ) -> None:
        """Atomically consume an independently pre-authorized proof ONCE.

        Raises PortalReplayFenceError on invalid or repeated evidence. Any
        integrity rejection occurs before a transaction is opened. This is a
        bookkeeping fence only: caller must perform authoritative admission.
        """
        if not portal_matches_reality_v1(
            proof, source=source, destination=destination,
            payload_digest=payload_digest, effect=effect,
            target_digest=target_digest, epoch=epoch,
        ):
            raise PortalReplayFenceError("canonical portal integrity required")

        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    """
                    INSERT INTO matrix_portal_consumed
                    (transit_digest, source_reality, destination_reality,
                     source_commitment, destination_commitment, payload_digest,
                     effect, target_digest, epoch)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        proof.transit_digest,
                        proof.source_reality, proof.destination_reality,
                        proof.source_commitment, proof.destination_commitment,
                        proof.payload_digest, proof.effect, proof.target_digest,
                        proof.epoch,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise PortalReplayFenceError(
                    "portal transit already consumed or ledger invariant failed"
                ) from error
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
