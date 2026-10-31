"""Local atomic metadata handoff: stage next native candidate, then rotate epoch.

One Continuity SQLite transaction marks the next epoch active, tombstones old
epoch, and records stage activation. NO running worker is replaced and NO
effect/secret authority is granted. Trust Plane, clocks and keys remain external.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import sqlite3
from typing import Callable

from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityV1,
    StrangeDurableContinuityError,
    _hex_digest,
    _trusted_seconds,
    _window,
)

_CTX = b"koschei/strange-epoch-handoff/v1\x00"
_WINDOW_SECONDS = 120


class StrangeEpochHandoffError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StrangeHandoffV1:
    continuity_id: str
    old_epoch: int
    next_epoch: int
    next_start_seconds: int
    deployment_id: str
    veyra_digest: str
    mir_fingerprint: str
    source_sha256: str
    native_sha256: str
    handoff_mac: str
    state: str
    authority: bool = False
    version: int = 1


def _secret(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise StrangeEpochHandoffError("handoff signing secret must contain 256 bits")
    return value


def _digest(value: str, field: str) -> str:
    try:
        return _hex_digest(value, field)
    except StrangeDurableContinuityError as exc:
        raise StrangeEpochHandoffError("invalid " + field) from exc


def _scope_id(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise StrangeEpochHandoffError("invalid deployment identity")
    return value


def _mac(key: bytes, item: StrangeHandoffV1) -> str:
    if item.version != 1 or item.authority is not False:
        raise StrangeEpochHandoffError("handoff cannot confer authority")
    if (
        not isinstance(item.old_epoch, int) or isinstance(item.old_epoch, bool)
        or not 1 <= item.old_epoch < 2**63 - 1
        or item.next_epoch != item.old_epoch + 1
        or not 0 <= item.next_start_seconds < 2**63
    ):
        raise StrangeEpochHandoffError("invalid handoff epoch")
    values = (
        item.continuity_id.encode("utf-8"),
        item.old_epoch.to_bytes(8, "big"),
        item.next_epoch.to_bytes(8, "big"),
        item.next_start_seconds.to_bytes(8, "big"),
        _scope_id(item.deployment_id).encode("utf-8"),
        bytes.fromhex(_digest(item.veyra_digest, "Veyra")),
        bytes.fromhex(_digest(item.mir_fingerprint, "MIR")),
        bytes.fromhex(_digest(item.source_sha256, "source")),
        bytes.fromhex(_digest(item.native_sha256, "native")),
    )
    return hmac.new(
        key,
        _CTX + b"".join(len(part).to_bytes(4, "big") + part for part in values),
        hashlib.sha256,
    ).hexdigest()


class StrangeEpochHandoffV1:
    """Use one durable Continuity DB; no distributed agreement or HSM custody."""

    def __init__(self, store: StrangeDurableContinuityV1):
        if not isinstance(store, StrangeDurableContinuityV1):
            raise StrangeEpochHandoffError("typed durable Continuity required")
        self.store = store
        with store._lock:
            store._db.execute(
                """CREATE TABLE IF NOT EXISTS strange_handoffs_v1 (
                   continuity_id TEXT NOT NULL,
                   old_epoch INTEGER NOT NULL CHECK(old_epoch > 0),
                   next_epoch INTEGER NOT NULL CHECK(next_epoch > old_epoch),
                   next_start_seconds INTEGER NOT NULL,
                   deployment_id TEXT NOT NULL,
                   veyra_digest TEXT NOT NULL,
                   mir_fingerprint TEXT NOT NULL,
                   source_sha256 TEXT NOT NULL,
                   native_sha256 TEXT NOT NULL,
                   handoff_mac TEXT NOT NULL,
                   state TEXT NOT NULL CHECK(state IN ('STAGED','ACTIVATED')),
                   PRIMARY KEY(continuity_id,old_epoch))"""
            )
            store._db.execute(
                """CREATE TABLE IF NOT EXISTS strange_handoff_retired_v1 (
                   continuity_id TEXT NOT NULL,
                   epoch INTEGER NOT NULL CHECK(epoch > 0),
                   handoff_mac TEXT NOT NULL,
                   PRIMARY KEY(continuity_id,epoch))"""
            )

    def _read(self, old_epoch: int) -> StrangeHandoffV1:
        row = self.store._db.execute(
            "SELECT continuity_id,old_epoch,next_epoch,next_start_seconds,"
            "deployment_id,veyra_digest,mir_fingerprint,source_sha256,"
            "native_sha256,handoff_mac,state FROM strange_handoffs_v1 "
            "WHERE continuity_id=? AND old_epoch=?",
            (self.store.continuity_id, old_epoch),
        ).fetchone()
        if row is None:
            raise StrangeEpochHandoffError("missing staged candidate")
        item = StrangeHandoffV1(*row)
        if item.continuity_id != self.store.continuity_id:
            raise StrangeEpochHandoffError("another Continuity root")
        return item

    def read(self, old_epoch: int) -> StrangeHandoffV1:
        with self.store._lock:
            return self._read(old_epoch)

    def stage(
        self, *, expected_old_epoch: int, expected_old_start_seconds: int,
        deployment_id: str, veyra_digest: str, mir_fingerprint: str,
        source_sha256: str, native_binary: bytes,
        seconds_reader: Callable[[], int], handoff_key: bytes,
    ) -> StrangeHandoffV1:
        """Record immutable proposed next binary; NOT future attestation."""
        key = _secret(handoff_key)
        _scope_id(deployment_id)
        for v, label in (
            (veyra_digest, "Veyra"), (mir_fingerprint, "MIR"),
            (source_sha256, "source"),
        ):
            _digest(v, label)
        if not isinstance(native_binary, bytes) or not 0 < len(native_binary) <= 32 * 1024 * 1024:
            raise StrangeEpochHandoffError("invalid bounded candidate binary")
        if (
            not isinstance(expected_old_epoch, int)
            or isinstance(expected_old_epoch, bool)
            or not 1 <= expected_old_epoch < 2**63 - 1
            or not isinstance(expected_old_start_seconds, int)
            or isinstance(expected_old_start_seconds, bool)
            or not 0 <= expected_old_start_seconds < 2**63 - 240
        ):
            raise StrangeEpochHandoffError("invalid old epoch window")
        base = StrangeHandoffV1(
            self.store.continuity_id, expected_old_epoch, expected_old_epoch + 1,
            expected_old_start_seconds + _WINDOW_SECONDS,
            deployment_id, veyra_digest, mir_fingerprint, source_sha256,
            hashlib.sha256(native_binary).hexdigest(), "", "STAGED",
        )
        item = StrangeHandoffV1(
            base.continuity_id, base.old_epoch, base.next_epoch,
            base.next_start_seconds, base.deployment_id, base.veyra_digest,
            base.mir_fingerprint, base.source_sha256, base.native_sha256,
            _mac(key, base), "STAGED",
        )
        with self.store._lock:
            try:
                self.store._db.execute("BEGIN IMMEDIATE")
                snap = self.store._snapshot(self.store._db.execute(
                    "SELECT continuity_id,epoch,starts_at_seconds FROM strange_continuity_v1 "
                    "WHERE continuity_id=?", (self.store.continuity_id,),
                ).fetchone())
                if snap.epoch != item.old_epoch or snap.starts_at_seconds != expected_old_start_seconds:
                    raise StrangeEpochHandoffError("stale or mismatched old epoch")
                _window(snap.epoch, snap.starts_at_seconds, _trusted_seconds(seconds_reader))
                self.store._db.execute(
                    "INSERT INTO strange_handoffs_v1 VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (item.continuity_id, item.old_epoch, item.next_epoch,
                     item.next_start_seconds, item.deployment_id, item.veyra_digest,
                     item.mir_fingerprint, item.source_sha256, item.native_sha256,
                     item.handoff_mac, item.state),
                )
                self.store._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self.store._db.execute("ROLLBACK")
                raise StrangeEpochHandoffError("next epoch already staged") from exc
            except Exception:
                self.store._db.execute("ROLLBACK")
                raise
        return item

    def activate(
        self, *, expected_old_epoch: int, expected_handoff_mac: str,
        seconds_reader: Callable[[], int], handoff_key: bytes,
    ) -> StrangeHandoffV1:
        """Commit stage, retire old and update Continuity in ONE transaction."""
        key = _secret(handoff_key)
        _digest(expected_handoff_mac, "handoff MAC")
        with self.store._lock:
            try:
                self.store._db.execute("BEGIN IMMEDIATE")
                head = self.store._snapshot(self.store._db.execute(
                    "SELECT continuity_id,epoch,starts_at_seconds FROM strange_continuity_v1 "
                    "WHERE continuity_id=?", (self.store.continuity_id,),
                ).fetchone())
                if head.epoch != expected_old_epoch:
                    raise StrangeEpochHandoffError("stale or already activated epoch")
                stage = self._read(expected_old_epoch)
                if (
                    stage.state != "STAGED"
                    or stage.next_epoch != head.epoch + 1
                    or stage.next_start_seconds != head.starts_at_seconds + _WINDOW_SECONDS
                ):
                    raise StrangeEpochHandoffError("stage does not match next scheduled window")
                expected = _mac(key, stage)
                if not (
                    hmac.compare_digest(expected_handoff_mac, expected)
                    and hmac.compare_digest(stage.handoff_mac, expected)
                ):
                    raise StrangeEpochHandoffError("staged identity/authentication mismatch")
                _window(stage.next_epoch, stage.next_start_seconds, _trusted_seconds(seconds_reader))
                update = self.store._db.execute(
                    "UPDATE strange_continuity_v1 SET epoch=?,starts_at_seconds=? "
                    "WHERE continuity_id=? AND epoch=?",
                    (stage.next_epoch, stage.next_start_seconds,
                     self.store.continuity_id, stage.old_epoch),
                )
                if update.rowcount != 1:
                    raise StrangeEpochHandoffError("Continuity CAS failed")
                self.store._db.execute(
                    "UPDATE strange_handoffs_v1 SET state='ACTIVATED' "
                    "WHERE continuity_id=? AND old_epoch=? AND state='STAGED'",
                    (self.store.continuity_id, stage.old_epoch),
                )
                self.store._db.execute(
                    "INSERT INTO strange_handoff_retired_v1 VALUES (?,?,?)",
                    (self.store.continuity_id, stage.old_epoch, stage.handoff_mac),
                )
                self.store._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self.store._db.execute("ROLLBACK")
                raise StrangeEpochHandoffError("retirement already committed") from exc
            except Exception:
                self.store._db.execute("ROLLBACK")
                raise
        return StrangeHandoffV1(
            stage.continuity_id, stage.old_epoch, stage.next_epoch,
            stage.next_start_seconds, stage.deployment_id, stage.veyra_digest,
            stage.mir_fingerprint, stage.source_sha256, stage.native_sha256,
            stage.handoff_mac, "ACTIVATED",
        )

    def retired(self, epoch: int) -> bool:
        with self.store._lock:
            return self.store._db.execute(
                "SELECT 1 FROM strange_handoff_retired_v1 "
                "WHERE continuity_id=? AND epoch=?",
                (self.store.continuity_id, epoch),
            ).fetchone() is not None
