"""Authenticated, decision-bound, request-bound execution permits for Koschei Lang v1.

External evidence is not authority. A permit may be minted only from an authenticated
canonical AuthorizationDecisionV1 whose outcome is allow. The permit is separately
HMAC-authenticated, binds the exact decision/evidence/subject/operation/request/epoch,
and must be consumed once through trusted replay state.

A successful consumption emits an authenticated receipt. The receipt proves that the
trusted bootstrap runtime accepted one exact permit consumption under one runtime key;
it does not prove that replay state is durably replicated or that the requested side
effect completed after consumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import string

from .authorization_decision_v1 import AuthorizationDecisionV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1

_CTX = b"koschei.execution-permit/v1\x00"
_CONSUME_CTX = b"koschei.execution-permit-consumption/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class ExecutionPermitV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionPermitV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ExecutionPermitV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise ExecutionPermitV1Error(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExecutionPermitV1Error(f"{label} must be a non-negative integer")
    return value


def _key(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ExecutionPermitV1Error(f"{label} must contain at least 32 bytes")
    return value


def _payload(*, decision_digest: str, evidence_digest: str, provider_id: str,
             consumer_id: str, subject_scope_digest: str, operation: str,
             request_digest: str, valid_epoch: int) -> bytes:
    rows = (
        f"decision={decision_digest}", f"evidence={evidence_digest}",
        f"provider={provider_id}", f"consumer={consumer_id}",
        f"subject={subject_scope_digest}", f"operation={operation}",
        f"request={request_digest}", f"epoch={valid_epoch}", "single_use=1",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


def _consumption_payload(*, permit_digest: str, decision_digest: str,
                         evidence_digest: str, operation: str,
                         request_digest: str, consumed_epoch: int) -> bytes:
    rows = (
        f"permit={permit_digest}",
        f"decision={decision_digest}",
        f"evidence={evidence_digest}",
        f"operation={operation}",
        f"request={request_digest}",
        f"epoch={consumed_epoch}",
        "consumed=1",
    )
    return _CONSUME_CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ExecutionPermitV1:
    authorization_decision_digest: str
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

    def assert_authenticated(self, *, runtime_key: bytes, decision_key: bytes,
                             grant: ExternalAdapterGrantV1,
                             evidence: ExternalAdapterEvidenceV1,
                             decision: AuthorizationDecisionV1) -> None:
        permit_key = _key(runtime_key, "runtime_key")
        grant.assert_sealed()
        evidence.assert_sealed(grant)
        decision.assert_authenticated(decision_key=decision_key, grant=grant, evidence=evidence)
        decision.assert_allows()
        if self.single_use is not True:
            raise ExecutionPermitV1Error("execution permit must remain single-use")
        decision_digest = _digest(self.authorization_decision_digest, "authorization_decision_digest")
        if decision_digest != decision.decision_digest:
            raise ExecutionPermitV1Error("execution permit belongs to different authorization decision")
        evidence_digest = _digest(self.evidence_digest, "evidence_digest")
        if evidence_digest != evidence.evidence_digest or evidence_digest != decision.evidence_digest:
            raise ExecutionPermitV1Error("execution permit belongs to different external evidence")
        provider = _text(self.provider_id, "provider_id")
        consumer = _text(self.consumer_id, "consumer_id")
        subject = _digest(self.subject_scope_digest, "subject_scope_digest")
        operation = _text(self.operation, "operation")
        request = _digest(self.request_digest, "request_digest")
        epoch = _epoch(self.valid_epoch, "valid_epoch")
        if provider != grant.provider_id or provider != decision.provider_id:
            raise ExecutionPermitV1Error("execution permit provider mismatch")
        if consumer != grant.consumer_id or consumer != decision.consumer_id:
            raise ExecutionPermitV1Error("execution permit consumer mismatch")
        if subject != grant.subject_scope_digest or subject != decision.subject_scope_digest:
            raise ExecutionPermitV1Error("execution permit subject mismatch")
        if operation != decision.operation:
            raise ExecutionPermitV1Error("execution permit operation differs from authorization decision")
        if request != decision.request_digest:
            raise ExecutionPermitV1Error("execution permit request differs from authorization decision")
        if epoch != evidence.observed_epoch or epoch != decision.decision_epoch:
            raise ExecutionPermitV1Error("execution permit epoch differs from authorization decision/evidence")
        expected = hmac.new(permit_key, _payload(
            decision_digest=decision_digest, evidence_digest=evidence_digest,
            provider_id=provider, consumer_id=consumer, subject_scope_digest=subject,
            operation=operation, request_digest=request, valid_epoch=epoch,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.permit_digest, expected):
            raise ExecutionPermitV1Error("execution permit authentication failed")

    def is_live_for(self, *, current_epoch: int, request_digest: str, operation: str) -> bool:
        return (
            _epoch(current_epoch, "current_epoch") == self.valid_epoch
            and _digest(request_digest, "request_digest") == self.request_digest
            and _text(operation, "operation") == self.operation
        )


@dataclass(frozen=True, slots=True)
class ExecutionConsumptionReceiptV1:
    permit_digest: str
    authorization_decision_digest: str
    evidence_digest: str
    operation: str
    request_digest: str
    consumed_epoch: int
    receipt_digest: str
    consumed: bool = True
    version: int = 1

    def assert_authenticated(self, *, runtime_key: bytes, permit: ExecutionPermitV1) -> None:
        key = _key(runtime_key, "runtime_key")
        if self.consumed is not True:
            raise ExecutionPermitV1Error("execution consumption receipt must remain consumed")
        permit_digest = _digest(self.permit_digest, "permit_digest")
        decision_digest = _digest(self.authorization_decision_digest, "authorization_decision_digest")
        evidence_digest = _digest(self.evidence_digest, "evidence_digest")
        operation = _text(self.operation, "operation")
        request = _digest(self.request_digest, "request_digest")
        epoch = _epoch(self.consumed_epoch, "consumed_epoch")
        expected_fields = (
            (permit_digest, permit.permit_digest, "permit"),
            (decision_digest, permit.authorization_decision_digest, "decision"),
            (evidence_digest, permit.evidence_digest, "evidence"),
            (operation, permit.operation, "operation"),
            (request, permit.request_digest, "request"),
            (epoch, permit.valid_epoch, "epoch"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise ExecutionPermitV1Error(f"execution consumption receipt {label} mismatch")
        expected = hmac.new(key, _consumption_payload(
            permit_digest=permit_digest,
            decision_digest=decision_digest,
            evidence_digest=evidence_digest,
            operation=operation,
            request_digest=request,
            consumed_epoch=epoch,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest, expected):
            raise ExecutionPermitV1Error("execution consumption receipt authentication failed")


def mint_execution_permit_v1(grant: ExternalAdapterGrantV1,
                             evidence: ExternalAdapterEvidenceV1,
                             decision: AuthorizationDecisionV1, *,
                             runtime_key: bytes, decision_key: bytes) -> ExecutionPermitV1:
    """Mint only from an authenticated allow decision; the caller cannot choose a wider operation."""
    permit_key = _key(runtime_key, "runtime_key")
    grant.assert_sealed()
    evidence.assert_sealed(grant)
    decision.assert_authenticated(decision_key=decision_key, grant=grant, evidence=evidence)
    decision.assert_allows()
    result = ExecutionPermitV1(
        authorization_decision_digest=decision.decision_digest,
        evidence_digest=evidence.evidence_digest,
        provider_id=grant.provider_id,
        consumer_id=grant.consumer_id,
        subject_scope_digest=grant.subject_scope_digest,
        operation=decision.operation,
        request_digest=decision.request_digest,
        valid_epoch=decision.decision_epoch,
        permit_digest="",
    )
    mac = hmac.new(permit_key, _payload(
        decision_digest=result.authorization_decision_digest,
        evidence_digest=result.evidence_digest, provider_id=result.provider_id,
        consumer_id=result.consumer_id, subject_scope_digest=result.subject_scope_digest,
        operation=result.operation, request_digest=result.request_digest,
        valid_epoch=result.valid_epoch,
    ), hashlib.sha256).hexdigest()
    object.__setattr__(result, "permit_digest", mac)
    result.assert_authenticated(runtime_key=permit_key, decision_key=decision_key,
                                grant=grant, evidence=evidence, decision=decision)
    return result


@dataclass(slots=True)
class ExecutionPermitLedgerV1:
    """Bootstrap single-use ledger; production requires durable shared monotonic state."""
    consumed: set[str] = field(default_factory=set)

    def consume(self, permit: ExecutionPermitV1, *, runtime_key: bytes,
                decision_key: bytes, grant: ExternalAdapterGrantV1,
                evidence: ExternalAdapterEvidenceV1, decision: AuthorizationDecisionV1,
                current_epoch: int, request_digest: str,
                operation: str) -> ExecutionConsumptionReceiptV1:
        permit.assert_authenticated(runtime_key=runtime_key, decision_key=decision_key,
                                    grant=grant, evidence=evidence, decision=decision)
        if not permit.is_live_for(current_epoch=current_epoch,
                                  request_digest=request_digest, operation=operation):
            raise ExecutionPermitV1Error("execution permit is not live for this request")
        if permit.permit_digest in self.consumed:
            raise ExecutionPermitV1Error("execution permit replay detected")
        self.consumed.add(permit.permit_digest)
        receipt = ExecutionConsumptionReceiptV1(
            permit_digest=permit.permit_digest,
            authorization_decision_digest=permit.authorization_decision_digest,
            evidence_digest=permit.evidence_digest,
            operation=permit.operation,
            request_digest=permit.request_digest,
            consumed_epoch=permit.valid_epoch,
            receipt_digest="",
        )
        mac = hmac.new(_key(runtime_key, "runtime_key"), _consumption_payload(
            permit_digest=receipt.permit_digest,
            decision_digest=receipt.authorization_decision_digest,
            evidence_digest=receipt.evidence_digest,
            operation=receipt.operation,
            request_digest=receipt.request_digest,
            consumed_epoch=receipt.consumed_epoch,
        ), hashlib.sha256).hexdigest()
        object.__setattr__(receipt, "receipt_digest", mac)
        receipt.assert_authenticated(runtime_key=runtime_key, permit=permit)
        return receipt
