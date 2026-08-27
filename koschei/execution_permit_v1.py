"""Authenticated, request-bound execution permits for Koschei Lang v1.

External evidence is not authority by itself. A trusted Koschei runtime may narrow
one sealed ExternalAdapterEvidenceV1 into one exact execution permit. The permit is
HMAC-authenticated with a runtime-held key, bound to one subject, operation,
request/challenge digest, evidence digest, and visibility epoch, and must be
consumed through a trusted ledger exactly once.

This is a bootstrap prototype. A Python in-memory ledger is not durable or
cross-process replay protection; a native runtime must preserve equivalent trusted
state and key custody.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import string

from .external_adapter_contract_v1 import (
    ExternalAdapterEvidenceV1,
    ExternalAdapterGrantV1,
)

_CTX = b"koschei.execution-permit/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class ExecutionPermitV1Error(ValueError):
    pass


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionPermitV1Error(f"{label} cannot be empty")
    return value.strip()


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ExecutionPermitV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered):
        raise ExecutionPermitV1Error(f"{label} must be hexadecimal")
    if lowered == "0" * 64:
        raise ExecutionPermitV1Error(f"{label} cannot be the zero digest")
    return lowered


def _require_epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExecutionPermitV1Error(f"{label} must be a non-negative integer")
    return value


def _require_key(runtime_key: bytes) -> bytes:
    if not isinstance(runtime_key, bytes) or len(runtime_key) < 32:
        raise ExecutionPermitV1Error("runtime_key must contain at least 32 bytes")
    return runtime_key


def _payload(
    *,
    evidence_digest: str,
    provider_id: str,
    consumer_id: str,
    subject_scope_digest: str,
    operation: str,
    request_digest: str,
    valid_epoch: int,
) -> bytes:
    rows = (
        f"evidence={evidence_digest}",
        f"provider={provider_id}",
        f"consumer={consumer_id}",
        f"subject={subject_scope_digest}",
        f"operation={operation}",
        f"request={request_digest}",
        f"epoch={valid_epoch}",
        "single_use=1",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


def _mac(runtime_key: bytes, payload: bytes) -> str:
    return hmac.new(runtime_key, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionPermitV1:
    evidence_digest: str
    provider_id: str
    consumer_id: str
    subject_scope_digest: str
    operation: str
    request_digest: str
    valid_epoch: int
    permit_digest: str
    single_use: bool = True
    version: int = 1

    def assert_authenticated(
        self,
        *,
        runtime_key: bytes,
        grant: ExternalAdapterGrantV1,
        evidence: ExternalAdapterEvidenceV1,
    ) -> None:
        key = _require_key(runtime_key)
        grant.assert_sealed()
        evidence.assert_sealed(grant)
        if self.single_use is not True:
            raise ExecutionPermitV1Error("execution permit must remain single-use")
        evidence_digest = _require_digest(self.evidence_digest, "evidence_digest")
        if evidence_digest != evidence.evidence_digest:
            raise ExecutionPermitV1Error("execution permit belongs to different external evidence")
        provider = _require_text(self.provider_id, "provider_id")
        consumer = _require_text(self.consumer_id, "consumer_id")
        if provider != grant.provider_id:
            raise ExecutionPermitV1Error("execution permit provider does not match grant")
        if consumer != grant.consumer_id:
            raise ExecutionPermitV1Error("execution permit consumer does not match grant")
        subject = _require_digest(self.subject_scope_digest, "subject_scope_digest")
        if subject != grant.subject_scope_digest:
            raise ExecutionPermitV1Error("execution permit subject does not match grant")
        operation = _require_text(self.operation, "operation")
        request = _require_digest(self.request_digest, "request_digest")
        epoch = _require_epoch(self.valid_epoch, "valid_epoch")
        if epoch != evidence.observed_epoch:
            raise ExecutionPermitV1Error("execution permit epoch must equal evidence observation epoch")
        expected = _mac(
            key,
            _payload(
                evidence_digest=evidence_digest,
                provider_id=provider,
                consumer_id=consumer,
                subject_scope_digest=subject,
                operation=operation,
                request_digest=request,
                valid_epoch=epoch,
            ),
        )
        if not hmac.compare_digest(self.permit_digest, expected):
            raise ExecutionPermitV1Error("execution permit authentication failed")

    def is_live_for(self, *, current_epoch: int, request_digest: str, operation: str) -> bool:
        epoch = _require_epoch(current_epoch, "current_epoch")
        request = _require_digest(request_digest, "request_digest")
        op = _require_text(operation, "operation")
        return epoch == self.valid_epoch and request == self.request_digest and op == self.operation


def mint_execution_permit_v1(
    grant: ExternalAdapterGrantV1,
    evidence: ExternalAdapterEvidenceV1,
    *,
    runtime_key: bytes,
    operation: str,
    request_digest: str,
) -> ExecutionPermitV1:
    """Narrow one sealed evidence object into one exact, authenticated execution request."""
    key = _require_key(runtime_key)
    grant.assert_sealed()
    evidence.assert_sealed(grant)
    operation = _require_text(operation, "operation")
    request = _require_digest(request_digest, "request_digest")
    epoch = _require_epoch(evidence.observed_epoch, "observed_epoch")
    result = ExecutionPermitV1(
        evidence_digest=evidence.evidence_digest,
        provider_id=grant.provider_id,
        consumer_id=grant.consumer_id,
        subject_scope_digest=grant.subject_scope_digest,
        operation=operation,
        request_digest=request,
        valid_epoch=epoch,
        permit_digest="",
    )
    object.__setattr__(
        result,
        "permit_digest",
        _mac(
            key,
            _payload(
                evidence_digest=result.evidence_digest,
                provider_id=result.provider_id,
                consumer_id=result.consumer_id,
                subject_scope_digest=result.subject_scope_digest,
                operation=result.operation,
                request_digest=result.request_digest,
                valid_epoch=result.valid_epoch,
            ),
        ),
    )
    result.assert_authenticated(runtime_key=key, grant=grant, evidence=evidence)
    return result


@dataclass(slots=True)
class ExecutionPermitLedgerV1:
    """Trusted single-use replay ledger for the bootstrap runtime boundary."""

    consumed: set[str] = field(default_factory=set)

    def consume(
        self,
        permit: ExecutionPermitV1,
        *,
        runtime_key: bytes,
        grant: ExternalAdapterGrantV1,
        evidence: ExternalAdapterEvidenceV1,
        current_epoch: int,
        request_digest: str,
        operation: str,
    ) -> None:
        permit.assert_authenticated(runtime_key=runtime_key, grant=grant, evidence=evidence)
        if not permit.is_live_for(
            current_epoch=current_epoch,
            request_digest=request_digest,
            operation=operation,
        ):
            raise ExecutionPermitV1Error("execution permit is not live for this request")
        if permit.permit_digest in self.consumed:
            raise ExecutionPermitV1Error("execution permit replay detected")
        self.consumed.add(permit.permit_digest)
