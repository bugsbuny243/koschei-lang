"""Durable authority revocation for Koschei Universe epoch tokens v1.

Epoch-bound tokens already become stale when lifecycle state or epoch changes. This
module adds an explicit durable revocation plane so catastrophic containment can
kill previously minted authority tokens even if a caller still holds the token
object and an old state snapshot.

Revocation is local and defensive. It does not perform external effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3
from threading import RLock

from .universe_epoch_token_v1 import SigilEpochToken
from .universe_nuclear_containment_v1 import NuclearContainmentReceipt

_CTX = b"koschei.universe-authority-revocation/v1\x00"


class AuthorityRevocationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RevocationRecord:
    activation_plan_digest: str
    epoch: int
    scope: str
    token_digest: str
    cause_digest: str
    record_digest: str


def _digest(plan: str, epoch: int, scope: str, token: str, cause: str) -> str:
    payload = "\n".join(
        (
            f"plan={plan}",
            f"epoch={epoch}",
            f"scope={scope}",
            f"token={token}",
            f"cause={cause}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


class DurableAuthorityRevocationRegistry:
    """Durable token/epoch revocation registry backed by one SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS authority_revocations (
                activation_plan_digest TEXT NOT NULL,
                epoch INTEGER NOT NULL CHECK(epoch >= 1),
                scope TEXT NOT NULL,
                token_digest TEXT NOT NULL,
                cause_digest TEXT NOT NULL,
                record_digest TEXT NOT NULL,
                PRIMARY KEY (activation_plan_digest, epoch, scope, token_digest)
            )
            """
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableAuthorityRevocationRegistry":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _insert(self, *, plan: str, epoch: int, scope: str, token: str, cause: str) -> RevocationRecord:
        if not plan or not cause:
            raise AuthorityRevocationError("revocation requires plan and cause digests")
        if epoch < 1:
            raise AuthorityRevocationError("revocation epoch must be positive")
        if scope not in {"TOKEN", "EPOCH"}:
            raise AuthorityRevocationError("invalid revocation scope")
        if scope == "TOKEN" and not token:
            raise AuthorityRevocationError("token revocation requires token digest")
        if scope == "EPOCH":
            token = "*"
        record = RevocationRecord(
            activation_plan_digest=plan,
            epoch=epoch,
            scope=scope,
            token_digest=token,
            cause_digest=cause,
            record_digest=_digest(plan, epoch, scope, token, cause),
        )
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT INTO authority_revocations VALUES (?,?,?,?,?,?)",
                    (
                        record.activation_plan_digest,
                        record.epoch,
                        record.scope,
                        record.token_digest,
                        record.cause_digest,
                        record.record_digest,
                    ),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                self._db.execute("ROLLBACK")
                raise AuthorityRevocationError("authority revocation already recorded") from error
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return record

    def revoke_token(self, token: SigilEpochToken, *, cause_digest: str) -> RevocationRecord:
        return self._insert(
            plan=token.activation_plan_digest,
            epoch=token.epoch,
            scope="TOKEN",
            token=token.token_digest,
            cause=cause_digest,
        )

    def revoke_epoch(self, *, plan_digest: str, epoch: int, cause_digest: str) -> RevocationRecord:
        return self._insert(
            plan=plan_digest,
            epoch=epoch,
            scope="EPOCH",
            token="*",
            cause=cause_digest,
        )

    def apply_nuclear_revocation(self, receipt: NuclearContainmentReceipt) -> RevocationRecord:
        """Kill all authority minted in the catastrophically contained epoch."""
        receipt.assert_sealed()
        return self.revoke_epoch(
            plan_digest=receipt.previous_state_digest + ":plan-unresolved",
            epoch=receipt.epoch,
            cause_digest=receipt.digest,
        )

    def apply_nuclear_revocation_for_plan(
        self,
        receipt: NuclearContainmentReceipt,
        *,
        activation_plan_digest: str,
    ) -> RevocationRecord:
        """Preferred nuclear binding when the Universe plan identity is available."""
        receipt.assert_sealed()
        return self.revoke_epoch(
            plan_digest=activation_plan_digest,
            epoch=receipt.epoch,
            cause_digest=receipt.digest,
        )

    def is_revoked(self, token: SigilEpochToken) -> bool:
        with self._lock:
            epoch_row = self._db.execute(
                "SELECT 1 FROM authority_revocations WHERE activation_plan_digest=? AND epoch=? "
                "AND scope='EPOCH' AND token_digest='*'",
                (token.activation_plan_digest, token.epoch),
            ).fetchone()
            if epoch_row is not None:
                return True
            token_row = self._db.execute(
                "SELECT 1 FROM authority_revocations WHERE activation_plan_digest=? AND epoch=? "
                "AND scope='TOKEN' AND token_digest=?",
                (token.activation_plan_digest, token.epoch, token.token_digest),
            ).fetchone()
            return token_row is not None

    def require_live(self, token: SigilEpochToken) -> None:
        if self.is_revoked(token):
            raise AuthorityRevocationError("authority token has been durably revoked")
