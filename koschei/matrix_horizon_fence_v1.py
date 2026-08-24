"""Durable Matrix/Hara Event Horizon fence v1.

Matrix admission is identity, not permanent reach. This module gives each Aevra
one durable current Hara. Moving to a new Matrix/Hara atomically tombstones the
old Hara and advances the current horizon. A stale Hara admission cannot return
through rollback or replay.

The target admission may be staged before the transition because MatrixAdmission
grants no authority by itself. Only the durable current Hara is eligible for the
strong Galaxy execution gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3
from threading import RLock

from .matrix_reality_v1 import MatrixAdmission

_CTX = b"koschei.matrix-horizon-fence/v1\x00"


class MatrixHorizonFenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HaraHead:
    veyra_digest: str
    aevra_digest: str
    matrix_digest: str
    hara_digest: str
    epoch: int
    previous_hara_digest: str | None
    cause_digest: str
    record_digest: str


def _record_digest(
    veyra: str,
    aevra: str,
    matrix: str,
    hara: str,
    epoch: int,
    previous: str | None,
    cause: str,
) -> str:
    payload = "\n".join(
        (
            f"veyra={veyra}",
            f"aevra={aevra}",
            f"matrix={matrix}",
            f"hara={hara}",
            f"epoch={epoch}",
            f"previous={previous or ''}",
            f"cause={cause}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


class DurableMatrixHorizonFence:
    """One current Hara per Aevra, with append-only old-Hara tombstones."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS matrix_hara_heads (
                aevra_digest TEXT PRIMARY KEY,
                veyra_digest TEXT NOT NULL,
                matrix_digest TEXT NOT NULL,
                hara_digest TEXT NOT NULL UNIQUE,
                epoch INTEGER NOT NULL CHECK(epoch >= 0),
                previous_hara_digest TEXT,
                cause_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS matrix_hara_tombstones (
                hara_digest TEXT PRIMARY KEY,
                aevra_digest TEXT NOT NULL,
                veyra_digest TEXT NOT NULL,
                death_epoch INTEGER NOT NULL CHECK(death_epoch >= 0),
                successor_hara_digest TEXT NOT NULL,
                cause_digest TEXT NOT NULL
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableMatrixHorizonFence":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def initialize(self, admission: MatrixAdmission, *, cause_digest: str = "matrix-genesis") -> HaraHead:
        if not cause_digest:
            raise MatrixHorizonFenceError("Matrix horizon genesis requires cause")
        digest = _record_digest(
            admission.veyra_digest,
            admission.aevra_digest,
            admission.matrix_digest,
            admission.hara_digest,
            admission.epoch,
            None,
            cause_digest,
        )
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO matrix_hara_heads VALUES (?,?,?,?,?,?,?,?)",
                    (
                        admission.aevra_digest,
                        admission.veyra_digest,
                        admission.matrix_digest,
                        admission.hara_digest,
                        admission.epoch,
                        None,
                        cause_digest,
                        digest,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise MatrixHorizonFenceError("Matrix horizon already initialized for Aevra") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return HaraHead(
            admission.veyra_digest,
            admission.aevra_digest,
            admission.matrix_digest,
            admission.hara_digest,
            admission.epoch,
            None,
            cause_digest,
            digest,
        )

    def current(self, aevra_digest: str) -> HaraHead | None:
        with self._lock:
            row = self._db.execute(
                "SELECT veyra_digest,aevra_digest,matrix_digest,hara_digest,epoch,"
                "previous_hara_digest,cause_digest,record_digest "
                "FROM matrix_hara_heads WHERE aevra_digest=?",
                (aevra_digest,),
            ).fetchone()
        if row is None:
            return None
        head = HaraHead(*row)
        expected = _record_digest(
            head.veyra_digest,
            head.aevra_digest,
            head.matrix_digest,
            head.hara_digest,
            head.epoch,
            head.previous_hara_digest,
            head.cause_digest,
        )
        if head.record_digest != expected:
            raise MatrixHorizonFenceError("Matrix Hara head integrity mismatch")
        return head

    def is_tombstoned(self, hara_digest: str) -> bool:
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM matrix_hara_tombstones WHERE hara_digest=?",
                (hara_digest,),
            ).fetchone() is not None

    def advance(
        self,
        previous: MatrixAdmission,
        successor: MatrixAdmission,
        *,
        cause_digest: str,
    ) -> HaraHead:
        """Cross one Matrix Event Horizon and make the old Hara permanently stale."""

        if not cause_digest:
            raise MatrixHorizonFenceError("Matrix transition requires cause")
        if previous.aevra_digest != successor.aevra_digest:
            raise MatrixHorizonFenceError("Matrix transition cannot move between Aevras")
        if previous.veyra_digest != successor.veyra_digest:
            raise MatrixHorizonFenceError("Matrix transition cannot move between Veyras")
        if previous.hara_digest == successor.hara_digest:
            raise MatrixHorizonFenceError("Matrix transition requires a new Hara")
        if previous.matrix_digest == successor.matrix_digest:
            raise MatrixHorizonFenceError("cross-Matrix transition requires a different Matrix")
        if successor.epoch != previous.epoch + 1:
            raise MatrixHorizonFenceError("Matrix transition requires exactly one next epoch")

        digest = _record_digest(
            successor.veyra_digest,
            successor.aevra_digest,
            successor.matrix_digest,
            successor.hara_digest,
            successor.epoch,
            previous.hara_digest,
            cause_digest,
        )
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                head = self._db.execute(
                    "SELECT hara_digest,epoch,veyra_digest FROM matrix_hara_heads WHERE aevra_digest=?",
                    (previous.aevra_digest,),
                ).fetchone()
                if head is None:
                    raise MatrixHorizonFenceError("Matrix horizon is not initialized for Aevra")
                if head[0] != previous.hara_digest or head[1] != previous.epoch or head[2] != previous.veyra_digest:
                    raise MatrixHorizonFenceError("previous Hara is not the durable current horizon")
                if self._db.execute(
                    "SELECT 1 FROM matrix_hara_tombstones WHERE hara_digest=?",
                    (previous.hara_digest,),
                ).fetchone() is not None:
                    raise MatrixHorizonFenceError("previous Hara is already Morth")

                self._db.execute(
                    "INSERT INTO matrix_hara_tombstones VALUES (?,?,?,?,?,?)",
                    (
                        previous.hara_digest,
                        previous.aevra_digest,
                        previous.veyra_digest,
                        previous.epoch,
                        successor.hara_digest,
                        cause_digest,
                    ),
                )
                changed = self._db.execute(
                    "UPDATE matrix_hara_heads SET matrix_digest=?,hara_digest=?,epoch=?,"
                    "previous_hara_digest=?,cause_digest=?,record_digest=? "
                    "WHERE aevra_digest=? AND hara_digest=? AND epoch=?",
                    (
                        successor.matrix_digest,
                        successor.hara_digest,
                        successor.epoch,
                        previous.hara_digest,
                        cause_digest,
                        digest,
                        previous.aevra_digest,
                        previous.hara_digest,
                        previous.epoch,
                    ),
                ).rowcount
                if changed != 1:
                    raise MatrixHorizonFenceError("concurrent Matrix horizon transition rejected")
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return HaraHead(
            successor.veyra_digest,
            successor.aevra_digest,
            successor.matrix_digest,
            successor.hara_digest,
            successor.epoch,
            previous.hara_digest,
            cause_digest,
            digest,
        )

    def require_current(self, admission: MatrixAdmission) -> HaraHead:
        head = self.current(admission.aevra_digest)
        if head is None:
            raise MatrixHorizonFenceError("no durable current Hara for Aevra")
        if self.is_tombstoned(admission.hara_digest):
            raise MatrixHorizonFenceError("Matrix admission Hara is Morth")
        if head.veyra_digest != admission.veyra_digest:
            raise MatrixHorizonFenceError("Matrix admission Veyra is not current")
        if head.matrix_digest != admission.matrix_digest:
            raise MatrixHorizonFenceError("Matrix admission Matrix is not current")
        if head.hara_digest != admission.hara_digest:
            raise MatrixHorizonFenceError("Matrix admission Hara is not current")
        if head.epoch != admission.epoch:
            raise MatrixHorizonFenceError("Matrix admission epoch is not current")
        return head
