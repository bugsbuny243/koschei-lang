"""Runtime-measured effect execution receipts for Koschei Lang v1.

A permit-consumption receipt proves that one exact permit was accepted. It does not
prove that the requested effect completed. This module closes only the next local
runtime link: the sanctioned executor validates the canonical request, validates
receipt key material, consumes the permit, invokes the effect itself, measures the
returned bytes or caught Exception, and authenticates that observation with a
dedicated effect key.

This is still not remote settlement/finality attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable

from .authorization_decision_v1 import AuthorizationDecisionV1
from .execution_permit_v1 import (
    ExecutionConsumptionReceiptV1,
    ExecutionPermitLedgerV1,
    ExecutionPermitV1,
)
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest

_CTX = b"koschei.effect-execution-receipt/v1\x00"
_RESULT_CTX = b"koschei.effect-result-measurement/v1\x00"
_FAILURE_CTX = b"koschei.effect-failure-measurement/v1\x00"
_OUTCOMES = frozenset({"effect-completed", "effect-failed"})


class EffectExecutionReceiptV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise EffectExecutionReceiptV1Error("effect_key must contain at least 32 bytes")
    return value


def _measurement_for_result(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise TypeError("effect callback must return bytes")
    return hashlib.sha256(_RESULT_CTX + value).hexdigest()


def _measurement_for_failure(error: Exception) -> str:
    label = f"{type(error).__module__}.{type(error).__qualname__}:{error}".encode("utf-8")
    return hashlib.sha256(_FAILURE_CTX + label).hexdigest()


def _payload(*, consumption_digest: str, permit_digest: str, decision_digest: str,
             request_digest: str, operation: str, epoch: int, outcome: str,
             measurement_digest: str) -> bytes:
    rows = (
        f"consumption={consumption_digest}",
        f"permit={permit_digest}",
        f"decision={decision_digest}",
        f"request={request_digest}",
        f"operation={operation}",
        f"epoch={epoch}",
        f"outcome={outcome}",
        f"measurement={measurement_digest}",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EffectExecutionReceiptV1:
    consumption_receipt_digest: str
    permit_digest: str
    authorization_decision_digest: str
    canonical_request_digest: str
    operation: str
    execution_epoch: int
    outcome: str
    measurement_digest: str
    receipt_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, effect_key: bytes,
                             consumption: ExecutionConsumptionReceiptV1,
                             permit: ExecutionPermitV1,
                             mir: NativeSigilMir,
                             request: CanonicalEffectRequest) -> None:
        key = _key(effect_key)
        mir.assert_sealed()
        request.assert_sealed(mir)
        if self.authority:
            raise EffectExecutionReceiptV1Error("effect receipt cannot carry ambient authority")
        if self.outcome not in _OUTCOMES:
            raise EffectExecutionReceiptV1Error("unknown effect execution outcome")
        expected_fields = (
            (self.consumption_receipt_digest, consumption.receipt_digest, "consumption"),
            (self.permit_digest, permit.permit_digest, "permit"),
            (self.authorization_decision_digest, permit.authorization_decision_digest, "decision"),
            (self.canonical_request_digest, request.digest, "request"),
            (self.operation, request.operation, "operation"),
            (self.execution_epoch, request.epoch, "epoch"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise EffectExecutionReceiptV1Error(f"effect receipt {label} mismatch")
        if permit.request_digest != request.digest or permit.operation != request.operation:
            raise EffectExecutionReceiptV1Error("effect request is outside execution permit")
        if permit.valid_epoch != request.epoch or consumption.consumed_epoch != request.epoch:
            raise EffectExecutionReceiptV1Error("effect epoch is outside consumed permit")
        if not isinstance(self.measurement_digest, str) or len(self.measurement_digest) != 64:
            raise EffectExecutionReceiptV1Error("effect measurement digest is invalid")
        expected = hmac.new(key, _payload(
            consumption_digest=self.consumption_receipt_digest,
            permit_digest=self.permit_digest,
            decision_digest=self.authorization_decision_digest,
            request_digest=self.canonical_request_digest,
            operation=self.operation,
            epoch=self.execution_epoch,
            outcome=self.outcome,
            measurement_digest=self.measurement_digest,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest, expected):
            raise EffectExecutionReceiptV1Error("effect execution receipt authentication failed")

    def assert_completed_result(self, result: bytes) -> None:
        if self.outcome != "effect-completed":
            raise EffectExecutionReceiptV1Error("effect receipt does not describe completion")
        if _measurement_for_result(result) != self.measurement_digest:
            raise EffectExecutionReceiptV1Error("effect result bytes do not match receipt measurement")


def execute_effect_with_receipt_v1(
    *,
    ledger: ExecutionPermitLedgerV1,
    permit: ExecutionPermitV1,
    runtime_key: bytes,
    decision_key: bytes,
    effect_key: bytes,
    grant: ExternalAdapterGrantV1,
    evidence: ExternalAdapterEvidenceV1,
    decision: AuthorizationDecisionV1,
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    current_epoch: int,
    effect: Callable[[CanonicalEffectRequest], bytes],
) -> tuple[ExecutionConsumptionReceiptV1, EffectExecutionReceiptV1, bytes | None]:
    """Validate first, consume once, invoke exact callback, attest local outcome."""
    if not callable(effect):
        raise EffectExecutionReceiptV1Error("effect must be callable")
    effect_key = _key(effect_key)
    mir.assert_sealed()
    request.assert_sealed(mir)
    if permit.request_digest != request.digest or permit.operation != request.operation:
        raise EffectExecutionReceiptV1Error("canonical request is outside execution permit")
    if permit.valid_epoch != request.epoch:
        raise EffectExecutionReceiptV1Error("canonical request epoch is outside execution permit")

    consumption = ledger.consume(
        permit,
        runtime_key=runtime_key,
        decision_key=decision_key,
        grant=grant,
        evidence=evidence,
        decision=decision,
        current_epoch=current_epoch,
        request_digest=request.digest,
        operation=request.operation,
    )

    result_bytes: bytes | None
    try:
        result_bytes = effect(request)
        measurement = _measurement_for_result(result_bytes)
        outcome = "effect-completed"
    except Exception as error:
        result_bytes = None
        measurement = _measurement_for_failure(error)
        outcome = "effect-failed"

    receipt = EffectExecutionReceiptV1(
        consumption_receipt_digest=consumption.receipt_digest,
        permit_digest=permit.permit_digest,
        authorization_decision_digest=permit.authorization_decision_digest,
        canonical_request_digest=request.digest,
        operation=request.operation,
        execution_epoch=request.epoch,
        outcome=outcome,
        measurement_digest=measurement,
        receipt_digest="",
    )
    mac = hmac.new(effect_key, _payload(
        consumption_digest=receipt.consumption_receipt_digest,
        permit_digest=receipt.permit_digest,
        decision_digest=receipt.authorization_decision_digest,
        request_digest=receipt.canonical_request_digest,
        operation=receipt.operation,
        epoch=receipt.execution_epoch,
        outcome=receipt.outcome,
        measurement_digest=receipt.measurement_digest,
    ), hashlib.sha256).hexdigest()
    object.__setattr__(receipt, "receipt_digest", mac)
    receipt.assert_authenticated(
        effect_key=effect_key, consumption=consumption, permit=permit,
        mir=mir, request=request,
    )
    return consumption, receipt, result_bytes
