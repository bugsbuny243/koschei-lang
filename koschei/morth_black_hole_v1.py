"""Koschei Morth / Event Horizon / Black Hole physics v1.

Morth is not a mutable disabled flag. Crossing the Event Horizon inserts an
immutable durable death record for one canonical Aevra. The durable store is the
first Black Hole slice: there is deliberately no delete, restore or unbury API.
Historical evidence remains readable, but the dead Aevra cannot participate in
new critical execution.

Rebirth is not resurrection. A later entity may use the same visible Koschei
subject, but it must possess a distinct Aevra identity born after the Morth epoch.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3
from threading import RLock
from typing import Callable, TypeVar

from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .native_sigil_atomic_execution_coordinator_v1 import AtomicClaim, AtomicExecutionCoordinator
from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof
from .sathra_request_binding_v1 import (
    SathraRequestBinding,
    enforce_atomic_sathra_bound_effect,
)
from .khar_sathra_v1 import Sathra

_CTX = b"koschei.morth-black-hole/v1\x00"
_T = TypeVar("_T")


class MorthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MorthRecord:
    veyra_digest: str
    aevra_digest: str
    death_epoch: int
    cause_digest: str
    evidence_digest: str
    record_digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.death_epoch < 0:
            raise MorthError("Morth death epoch cannot be negative")
        if not all(
            isinstance(value, str) and value
            for value in (
                self.veyra_digest,
                self.aevra_digest,
                self.cause_digest,
                self.evidence_digest,
            )
        ):
            raise MorthError("Morth record fields cannot be empty")
        expected = _record_digest(
            self.veyra_digest,
            self.aevra_digest,
            self.death_epoch,
            self.cause_digest,
            self.evidence_digest,
        )
        if self.record_digest != expected:
            raise MorthError("Morth record seal mismatch")


def _record_digest(
    veyra_digest: str,
    aevra_digest: str,
    death_epoch: int,
    cause_digest: str,
    evidence_digest: str,
) -> str:
    payload = "\n".join(
        (
            f"veyra={veyra_digest}",
            f"aevra={aevra_digest}",
            f"death-epoch={death_epoch}",
            f"cause={cause_digest}",
            f"evidence={evidence_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


class DurableBlackHole:
    """Append-only durable terminal sink for dead Aevra identities."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS morth_aevra (
                aevra_digest TEXT PRIMARY KEY,
                veyra_digest TEXT NOT NULL,
                death_epoch INTEGER NOT NULL CHECK(death_epoch >= 0),
                cause_digest TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableBlackHole":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def enter_event_horizon(
        self,
        aevra: AevraIdentity,
        veyra: VeyraIdentity,
        mir: NativeSigilMir,
        *,
        death_epoch: int,
        cause_digest: str,
        evidence_digest: str,
    ) -> MorthRecord:
        """Irreversibly place one Aevra into Morth.

        No method exists to reverse this insertion. A caller wanting a future
        entity must birth a different Aevra identity.
        """

        try:
            veyra.assert_sealed()
            mir.assert_sealed()
            aevra.assert_sealed(veyra, mir)
        except ValueError as error:
            raise MorthError(str(error)) from error
        if not isinstance(death_epoch, int) or death_epoch < aevra.birth_epoch:
            raise MorthError("Morth death cannot predate Aevra birth")
        if not cause_digest or not evidence_digest:
            raise MorthError("Morth requires cause and evidence")
        digest = _record_digest(
            veyra.digest,
            aevra.digest,
            death_epoch,
            cause_digest,
            evidence_digest,
        )
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO morth_aevra VALUES (?,?,?,?,?,?)",
                    (
                        aevra.digest,
                        veyra.digest,
                        death_epoch,
                        cause_digest,
                        evidence_digest,
                        digest,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise MorthError("Aevra has already crossed the Event Horizon") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        record = MorthRecord(
            veyra.digest,
            aevra.digest,
            death_epoch,
            cause_digest,
            evidence_digest,
            digest,
        )
        record.assert_sealed()
        return record

    def record(self, aevra_digest: str) -> MorthRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT veyra_digest,aevra_digest,death_epoch,cause_digest,evidence_digest,record_digest "
                "FROM morth_aevra WHERE aevra_digest=?",
                (aevra_digest,),
            ).fetchone()
        if row is None:
            return None
        result = MorthRecord(*row)
        result.assert_sealed()
        return result

    def is_morth(self, aevra: AevraIdentity, veyra: VeyraIdentity) -> bool:
        row = self.record(aevra.digest)
        if row is None:
            return False
        if row.veyra_digest != veyra.digest:
            raise MorthError("Morth Aevra/Veyra identity mismatch")
        return True

    def require_living(
        self,
        aevra: AevraIdentity,
        veyra: VeyraIdentity,
        mir: NativeSigilMir,
    ) -> None:
        try:
            aevra.assert_sealed(veyra, mir)
        except ValueError as error:
            raise MorthError(str(error)) from error
        if self.is_morth(aevra, veyra):
            raise MorthError("Aevra is Morth and has no living future")

    def require_rebirth_not_resurrection(
        self,
        old: AevraIdentity,
        new: AevraIdentity,
        veyra: VeyraIdentity,
        old_mir: NativeSigilMir,
        new_mir: NativeSigilMir,
    ) -> MorthRecord:
        """Require a new identity born after death; never revive the old Aevra."""

        try:
            old.assert_sealed(veyra, old_mir)
            new.assert_sealed(veyra, new_mir)
        except ValueError as error:
            raise MorthError(str(error)) from error
        record = self.record(old.digest)
        if record is None or record.veyra_digest != veyra.digest:
            raise MorthError("rebirth requires the old Aevra to be Morth")
        if new.digest == old.digest:
            raise MorthError("rebirth cannot resurrect the same Aevra identity")
        if new.birth_epoch <= record.death_epoch:
            raise MorthError("reborn Aevra must be born after the Morth epoch")
        return record


def enforce_living_atomic_sathra_effect(
    black_hole: DurableBlackHole,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    request_bound_proof: RequestBoundProof,
    sathra: Sathra,
    sathra_binding: SathraRequestBinding,
    coordinator: AtomicExecutionCoordinator,
    effect: Callable[[CanonicalEffectRequest], _T],
) -> tuple[EnforcementDecision, _T | None, AtomicClaim]:
    """Critical execution gate that refuses any Aevra already in Morth."""

    black_hole.require_living(aevra, veyra, mir)
    return enforce_atomic_sathra_bound_effect(
        mir,
        veyra,
        aevra,
        request,
        proof,
        request_bound_proof,
        sathra,
        sathra_binding,
        coordinator,
        effect,
    )
