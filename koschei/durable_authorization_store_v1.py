"""Durable local authorization-head and execution-claim store for Koschei Lang v1.

The current authorization-head check and single-use permit claim are serialized
in one SQLite ``BEGIN IMMEDIATE`` transaction and survive process restart.  The
filesystem path is explicit trusted-host input; project/model/tool metadata never
selects this store or widens authority.

A committed claim proves only local admission at one exact current head.  It is
not remote side-effect settlement, distributed consensus, remote revocation
freshness, or OS confinement.  Crash after claim and before effect is fail-closed:
the permit remains claimed and is not automatically retried.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import sqlite3
from typing import Iterator

from .authorization_decision_v1 import AuthorizationDecisionV1
from .authorization_state_ledger_v1 import AuthorizationStateLedgerV1
from .authorization_transition_v1 import (
    AuthorizationStateV1,
    AuthorizationTransitionV1,
    DelegationLinkV1,
    ExecutionAuthorizationSnapshotV1,
    IntentCommitmentV1,
    authorization_snapshot_for_execution_v1,
)
from .execution_permit_v1 import ExecutionPermitV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .fresh_effect_authorization_v1 import assert_effect_authorization_binding_v1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest

_SCHEMA_VERSION = "1"
_CLAIM_CTX = b"koschei.durable-execution-claim/v1\x00"
_REQUIRED_COLUMNS = {
    "authorization_heads": {"subject", "state_digest", "state_epoch", "state_status", "intent_commitment_digest"},
    "authorization_transitions": {"transition_digest", "subject", "previous_state_digest", "next_state_digest", "transition_epoch", "transition_kind"},
    "execution_claims": {"permit_digest", "subject", "state_digest", "snapshot_digest", "authorization_decision_digest", "evidence_digest", "request_digest", "operation", "execution_epoch", "claim_receipt_digest"},
}


class DurableAuthorizationStoreV1Error(RuntimeError):
    """Raised when durable authorization state cannot be trusted or committed."""


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise DurableAuthorizationStoreV1Error("claim_key must contain at least 32 bytes")
    return value


def _claim_payload(*, permit: str, state: str, snapshot: str, decision: str,
                   evidence: str, request: str, operation: str, epoch: int) -> bytes:
    rows = (
        f"permit={permit}", f"state={state}", f"snapshot={snapshot}",
        f"decision={decision}", f"evidence={evidence}", f"request={request}",
        f"operation={operation}", f"epoch={epoch}", "claimed=1",
    )
    return _CLAIM_CTX + "\n".join(rows).encode()


@dataclass(frozen=True, slots=True)
class DurableExecutionClaimReceiptV1:
    permit_digest: str
    state_digest: str
    snapshot_digest: str
    authorization_decision_digest: str
    evidence_digest: str
    request_digest: str
    operation: str
    execution_epoch: int
    receipt_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, claim_key: bytes, state: AuthorizationStateV1,
                             snapshot: ExecutionAuthorizationSnapshotV1,
                             permit: ExecutionPermitV1) -> None:
        key = _key(claim_key)
        if self.authority:
            raise DurableAuthorizationStoreV1Error("durable execution claim cannot carry ambient authority")
        expected = (
            (self.permit_digest, permit.permit_digest, "permit"),
            (self.state_digest, state.state_digest, "state"),
            (self.snapshot_digest, snapshot.snapshot_digest, "snapshot"),
            (self.authorization_decision_digest, permit.authorization_decision_digest, "decision"),
            (self.evidence_digest, permit.evidence_digest, "evidence"),
            (self.request_digest, permit.request_digest, "request"),
            (self.operation, permit.operation, "operation"),
            (self.execution_epoch, snapshot.execution_epoch, "epoch"),
        )
        for actual, wanted, label in expected:
            if actual != wanted:
                raise DurableAuthorizationStoreV1Error(f"durable execution claim {label} mismatch")
        mac = hmac.new(key, _claim_payload(
            permit=self.permit_digest, state=self.state_digest,
            snapshot=self.snapshot_digest, decision=self.authorization_decision_digest,
            evidence=self.evidence_digest, request=self.request_digest,
            operation=self.operation, epoch=self.execution_epoch,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest, mac):
            raise DurableAuthorizationStoreV1Error("durable execution claim authentication failed")


@dataclass(frozen=True, slots=True)
class DurableAuthorizationStoreV1:
    """Explicit-path SQLite ledger for one trusted local Lang runtime boundary."""

    path: Path
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        path = Path(self.path)
        if str(path) in {"", ":memory:"}:
            raise DurableAuthorizationStoreV1Error("durable authorization store requires a filesystem path")
        if path.exists() and not path.is_file():
            raise DurableAuthorizationStoreV1Error("durable authorization store path is not a file")
        if not path.parent.is_dir():
            raise DurableAuthorizationStoreV1Error("durable authorization store parent directory is unavailable")
        if (not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool)
                or self.timeout_seconds <= 0):
            raise DurableAuthorizationStoreV1Error("timeout_seconds must be positive")
        object.__setattr__(self, "path", path)
        self._initialize()

    def _open(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(self.path), timeout=float(self.timeout_seconds), isolation_level=None)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA busy_timeout = {int(float(self.timeout_seconds) * 1000)}")
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
            if mode is None or str(mode[0]).lower() != "wal":
                conn.close()
                raise DurableAuthorizationStoreV1Error("durable authorization store requires WAL mode")
            conn.execute("PRAGMA synchronous = FULL")
            return conn
        except DurableAuthorizationStoreV1Error:
            raise
        except sqlite3.Error:
            raise DurableAuthorizationStoreV1Error("durable authorization store is unavailable") from None

    @staticmethod
    def _validate_schema(conn: sqlite3.Connection) -> None:
        try:
            row = conn.execute("SELECT value FROM koschei_store_metadata WHERE key='schema_version'").fetchone()
            if row is None or row[0] != _SCHEMA_VERSION:
                raise DurableAuthorizationStoreV1Error("durable authorization schema version is unavailable")
            for table, required in _REQUIRED_COLUMNS.items():
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if not required.issubset(columns):
                    raise DurableAuthorizationStoreV1Error(f"durable authorization schema for {table} is incomplete")
            executable_schema = conn.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE type IN ('trigger', 'view') ORDER BY type, name LIMIT 1"
            ).fetchone()
            if executable_schema is not None:
                raise DurableAuthorizationStoreV1Error(
                    "durable authorization store contains unsupported executable schema object"
                )
        except DurableAuthorizationStoreV1Error:
            raise
        except sqlite3.Error:
            raise DurableAuthorizationStoreV1Error("durable authorization schema validation failed") from None

    def _initialize(self) -> None:
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS koschei_store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = conn.execute("SELECT value FROM koschei_store_metadata WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute("INSERT INTO koschei_store_metadata VALUES('schema_version', ?)", (_SCHEMA_VERSION,))
            elif row[0] != _SCHEMA_VERSION:
                raise DurableAuthorizationStoreV1Error("unsupported durable authorization schema version")
            conn.execute("CREATE TABLE IF NOT EXISTS authorization_heads (subject TEXT PRIMARY KEY, state_digest TEXT NOT NULL, state_epoch INTEGER NOT NULL, state_status TEXT NOT NULL, intent_commitment_digest TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS authorization_transitions (transition_digest TEXT PRIMARY KEY, subject TEXT NOT NULL, previous_state_digest TEXT NOT NULL, next_state_digest TEXT NOT NULL, transition_epoch INTEGER NOT NULL, transition_kind TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS execution_claims (permit_digest TEXT PRIMARY KEY, subject TEXT NOT NULL, state_digest TEXT NOT NULL, snapshot_digest TEXT NOT NULL, authorization_decision_digest TEXT NOT NULL, evidence_digest TEXT NOT NULL, request_digest TEXT NOT NULL, operation TEXT NOT NULL, execution_epoch INTEGER NOT NULL, claim_receipt_digest TEXT NOT NULL)")
            self._validate_schema(conn)
            conn.commit()
        except DurableAuthorizationStoreV1Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise DurableAuthorizationStoreV1Error("durable authorization schema initialization failed") from None
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Validate after acquiring the writer lock so schema/version cannot
            # change between validation and the authoritative head/claim write.
            self._validate_schema(conn)
            yield conn
            conn.commit()
        except DurableAuthorizationStoreV1Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise DurableAuthorizationStoreV1Error("durable authorization store operation failed") from None
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._open()
        try:
            self._validate_schema(conn)
            yield conn
        except DurableAuthorizationStoreV1Error:
            raise
        except sqlite3.Error:
            raise DurableAuthorizationStoreV1Error("durable authorization store operation failed") from None
        finally:
            conn.close()

    def register_initial(self, state: AuthorizationStateV1) -> None:
        AuthorizationStateLedgerV1._assert_sealed(state)
        if state.previous_state_digest is not None or state.status != "active":
            raise DurableAuthorizationStoreV1Error("initial authorization state must be active with no predecessor")
        with self._transaction() as conn:
            try:
                conn.execute("INSERT INTO authorization_heads VALUES(?, ?, ?, ?, ?)", (
                    state.subject, state.state_digest, state.epoch, state.status,
                    state.intent_commitment_digest,
                ))
            except sqlite3.IntegrityError:
                raise DurableAuthorizationStoreV1Error("authorization state head already exists") from None

    def commit_transition(self, previous: AuthorizationStateV1, next_state: AuthorizationStateV1,
                          transition: AuthorizationTransitionV1) -> None:
        AuthorizationStateLedgerV1._assert_sealed(previous)
        AuthorizationStateLedgerV1._assert_sealed(next_state)
        AuthorizationStateLedgerV1._assert_transition_sealed(transition)
        if previous.subject != next_state.subject:
            raise DurableAuthorizationStoreV1Error("authorization transition changes subject")
        if next_state.previous_state_digest != previous.state_digest:
            raise DurableAuthorizationStoreV1Error("next authorization state predecessor mismatch")
        if transition.previous_state_digest != previous.state_digest or transition.next_state_digest != next_state.state_digest:
            raise DurableAuthorizationStoreV1Error("authorization transition state binding mismatch")
        if transition.epoch != next_state.epoch:
            raise DurableAuthorizationStoreV1Error("authorization transition epoch mismatch")
        with self._transaction() as conn:
            row = conn.execute("SELECT state_digest FROM authorization_heads WHERE subject=?", (previous.subject,)).fetchone()
            if row is None:
                raise DurableAuthorizationStoreV1Error("authorization state head is unavailable")
            if row[0] != previous.state_digest:
                raise DurableAuthorizationStoreV1Error("authorization state is not the current durable monotonic head")
            changed = conn.execute("UPDATE authorization_heads SET state_digest=?, state_epoch=?, state_status=?, intent_commitment_digest=? WHERE subject=? AND state_digest=?", (
                next_state.state_digest, next_state.epoch, next_state.status,
                next_state.intent_commitment_digest, previous.subject, previous.state_digest,
            ))
            if changed.rowcount != 1:
                raise DurableAuthorizationStoreV1Error("authorization state compare-and-swap failed")
            try:
                conn.execute("INSERT INTO authorization_transitions VALUES(?, ?, ?, ?, ?, ?)", (
                    transition.transition_digest, previous.subject, previous.state_digest,
                    next_state.state_digest, transition.epoch, transition.kind,
                ))
            except sqlite3.IntegrityError:
                raise DurableAuthorizationStoreV1Error("authorization transition replay detected") from None

    def claim_execution(self, *, state: AuthorizationStateV1,
                        delegation_chain: tuple[DelegationLinkV1, ...],
                        intent: IntentCommitmentV1, permit: ExecutionPermitV1,
                        runtime_key: bytes, decision_key: bytes,
                        grant: ExternalAdapterGrantV1, evidence: ExternalAdapterEvidenceV1,
                        decision: AuthorizationDecisionV1, mir: NativeSigilMir,
                        request: CanonicalEffectRequest, current_epoch: int,
                        claim_key: bytes) -> tuple[ExecutionAuthorizationSnapshotV1, DurableExecutionClaimReceiptV1]:
        key = _key(claim_key)
        # Exact binding lives inside the durable primitive, not just a wrapper;
        # direct callers therefore cannot bypass intent/identity/scope checks.
        assert_effect_authorization_binding_v1(
            state=state, intent=intent, grant=grant, mir=mir,
            request=request, current_epoch=current_epoch,
        )
        AuthorizationStateLedgerV1._assert_sealed(state)
        snapshot = authorization_snapshot_for_execution_v1(
            state, delegation_chain, execution_epoch=current_epoch,
        )
        permit.assert_authenticated(
            runtime_key=runtime_key, decision_key=decision_key,
            grant=grant, evidence=evidence, decision=decision,
        )
        if not permit.is_live_for(current_epoch=current_epoch, request_digest=request.digest,
                                  operation=request.operation):
            raise DurableAuthorizationStoreV1Error("execution permit is not live for durable claim")

        receipt = DurableExecutionClaimReceiptV1(
            permit_digest=permit.permit_digest, state_digest=state.state_digest,
            snapshot_digest=snapshot.snapshot_digest,
            authorization_decision_digest=permit.authorization_decision_digest,
            evidence_digest=permit.evidence_digest, request_digest=permit.request_digest,
            operation=permit.operation, execution_epoch=current_epoch, receipt_digest="",
        )
        mac = hmac.new(key, _claim_payload(
            permit=receipt.permit_digest, state=receipt.state_digest,
            snapshot=receipt.snapshot_digest, decision=receipt.authorization_decision_digest,
            evidence=receipt.evidence_digest, request=receipt.request_digest,
            operation=receipt.operation, epoch=receipt.execution_epoch,
        ), hashlib.sha256).hexdigest()
        object.__setattr__(receipt, "receipt_digest", mac)
        receipt.assert_authenticated(claim_key=key, state=state, snapshot=snapshot, permit=permit)

        with self._transaction() as conn:
            row = conn.execute("SELECT state_digest, state_epoch, state_status, intent_commitment_digest FROM authorization_heads WHERE subject=?", (state.subject,)).fetchone()
            if row is None:
                raise DurableAuthorizationStoreV1Error("authorization state head is unavailable")
            if row[0] != state.state_digest:
                raise DurableAuthorizationStoreV1Error("authorization state is not the current durable monotonic head")
            if row[1] != state.epoch or row[2] != "active":
                raise DurableAuthorizationStoreV1Error("durable authorization state is not active")
            if row[3] != state.intent_commitment_digest:
                raise DurableAuthorizationStoreV1Error("durable authorization intent binding mismatch")
            try:
                conn.execute("INSERT INTO execution_claims VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    receipt.permit_digest, state.subject, receipt.state_digest,
                    receipt.snapshot_digest, receipt.authorization_decision_digest,
                    receipt.evidence_digest, receipt.request_digest, receipt.operation,
                    receipt.execution_epoch, receipt.receipt_digest,
                ))
            except sqlite3.IntegrityError:
                raise DurableAuthorizationStoreV1Error("execution permit replay detected") from None
        return snapshot, receipt

    def current_head_digest(self, subject: str) -> str | None:
        with self._read() as conn:
            row = conn.execute("SELECT state_digest FROM authorization_heads WHERE subject=?", (subject,)).fetchone()
            return None if row is None else str(row[0])

    def has_execution_claim(self, permit_digest: str) -> bool:
        with self._read() as conn:
            return conn.execute("SELECT 1 FROM execution_claims WHERE permit_digest=?", (permit_digest,)).fetchone() is not None
