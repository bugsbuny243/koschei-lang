"""Durable-claim effect execution for Koschei Lang v1.

The callback is unreachable until the durable authorization store commits an
execution claim against the exact current authorization head. The existing
runtime-measured effect receipt remains the outcome evidence format; this module
adds durable replay/revocation ordering without changing strict V1 permits.

A committed durable claim is intentionally fail-closed. If the process crashes
between claim commit and callback completion, the permit remains claimed and is
not retried automatically. This module does not claim remote exactly-once side
effects or distributed transaction semantics.
"""
from __future__ import annotations

from typing import Callable

from .authorization_decision_v1 import AuthorizationDecisionV1
from .authorization_transition_v1 import (
    AuthorizationStateV1,
    DelegationLinkV1,
    ExecutionAuthorizationSnapshotV1,
    IntentCommitmentV1,
)
from .durable_authorization_store_v1 import (
    DurableAuthorizationStoreV1,
    DurableExecutionClaimReceiptV1,
)
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1, execute_effect_with_receipt_v1
from .execution_permit_v1 import ExecutionConsumptionReceiptV1, ExecutionPermitLedgerV1, ExecutionPermitV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .fresh_effect_authorization_v1 import assert_effect_authorization_binding_v1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest


class DurableEffectExecutionV1Error(ValueError):
    """Raised before a durable claim when the local executor inputs are unusable."""


def execute_effect_with_durable_authorization_v1(
    *,
    store: DurableAuthorizationStoreV1,
    state: AuthorizationStateV1,
    delegation_chain: tuple[DelegationLinkV1, ...],
    intent: IntentCommitmentV1,
    permit: ExecutionPermitV1,
    runtime_key: bytes,
    decision_key: bytes,
    claim_key: bytes,
    effect_key: bytes,
    grant: ExternalAdapterGrantV1,
    evidence: ExternalAdapterEvidenceV1,
    decision: AuthorizationDecisionV1,
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    current_epoch: int,
    effect: Callable[[CanonicalEffectRequest], bytes],
) -> tuple[
    ExecutionAuthorizationSnapshotV1,
    DurableExecutionClaimReceiptV1,
    ExecutionConsumptionReceiptV1,
    EffectExecutionReceiptV1,
    bytes | None,
]:
    """Bind -> atomically durable-claim -> consume bootstrap permit -> invoke effect."""

    if not isinstance(store, DurableAuthorizationStoreV1):
        raise DurableEffectExecutionV1Error("durable authorization store is required")
    if not callable(effect):
        raise DurableEffectExecutionV1Error("effect must be callable")
    if not isinstance(effect_key, bytes) or len(effect_key) < 32:
        raise DurableEffectExecutionV1Error("effect_key must contain at least 32 bytes")

    assert_effect_authorization_binding_v1(
        state=state,
        intent=intent,
        grant=grant,
        mir=mir,
        request=request,
        current_epoch=current_epoch,
    )
    snapshot, durable_claim = store.claim_execution(
        state=state,
        delegation_chain=delegation_chain,
        permit=permit,
        runtime_key=runtime_key,
        decision_key=decision_key,
        grant=grant,
        evidence=evidence,
        decision=decision,
        current_epoch=current_epoch,
        request_digest=request.digest,
        operation=request.operation,
        claim_key=claim_key,
    )

    # The durable claim is now the replay authority. A fresh in-memory permit
    # ledger is used only to preserve the existing strict consumption/effect
    # receipt chain; it is not relied on for restart-safe replay prevention.
    consumption, effect_receipt, result = execute_effect_with_receipt_v1(
        ledger=ExecutionPermitLedgerV1(),
        permit=permit,
        runtime_key=runtime_key,
        decision_key=decision_key,
        effect_key=effect_key,
        grant=grant,
        evidence=evidence,
        decision=decision,
        mir=mir,
        request=request,
        current_epoch=current_epoch,
        effect=effect,
    )
    return snapshot, durable_claim, consumption, effect_receipt, result
