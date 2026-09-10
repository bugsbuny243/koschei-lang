"""Fresh execution-time authorization guard for Koschei effect execution v1.

This module is additive. It does not mutate the strict AuthorizationDecisionV1 or
ExecutionPermitV1 schemas and it does not create a second authority system.
Instead, it binds the existing current-state/delegation snapshot primitive to a
new hardened effect path immediately before the existing permit-consumption and
runtime-measured effect executor.

The guard is intentionally conservative: one canonical request maps to one
canonical execution principal and one exact effective constraint profile. A
fresh snapshot is evidence that the in-process authorization ledger considered
that state current at the execution epoch; the snapshot itself carries no
ambient authority.

Security boundary: AuthorizationStateLedgerV1 and ExecutionPermitLedgerV1 are
currently in-memory bootstrap ledgers and their checks are not one durable,
cross-process transaction. This module therefore closes the missing local
sequencing/binding gap but does not claim production-grade revocation-race or
OS-confinement acceptance.
"""
from __future__ import annotations

import string
from typing import Callable

from .authorization_decision_v1 import AuthorizationDecisionV1
from .authorization_state_ledger_v1 import AuthorizationStateLedgerV1
from .authorization_transition_v1 import (
    AuthorizationStateV1,
    DelegationLinkV1,
    ExecutionAuthorizationSnapshotV1,
    IntentCommitmentV1,
)
from .canonical_authority_basis_v1 import canonical_subject_scope_digest_v1
from .effect_execution_receipt_v1 import EffectExecutionReceiptV1, execute_effect_with_receipt_v1
from .execution_permit_v1 import (
    ExecutionConsumptionReceiptV1,
    ExecutionPermitLedgerV1,
    ExecutionPermitV1,
)
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest

_HEX = frozenset(string.hexdigits.lower())
_PRINCIPAL_PREFIX = "koschei:canonical-identity:v1:"


class FreshEffectAuthorizationV1Error(ValueError):
    """Raised when a request cannot prove fresh, exact execution authority."""


def canonical_execution_principal_v1(request: CanonicalEffectRequest) -> str:
    """Map the request's sealed identity digest to the v1 authorization principal."""

    digest = request.identity_digest
    if not isinstance(digest, str) or len(digest) != 64:
        raise FreshEffectAuthorizationV1Error("canonical request identity digest is invalid")
    if digest != digest.lower() or any(ch not in _HEX for ch in digest) or digest == "0" * 64:
        raise FreshEffectAuthorizationV1Error("canonical request identity digest is invalid")
    return _PRINCIPAL_PREFIX + digest


def _assert_exact_effect_constraints(
    state: AuthorizationStateV1,
    *,
    request: CanonicalEffectRequest,
    grant: ExternalAdapterGrantV1,
) -> None:
    constraints = state.effective_constraints
    expected = (
        (constraints.resources, (request.subject,), "resource"),
        (constraints.operations, (request.operation,), "operation"),
        (constraints.arguments, (request.request_digest,), "argument"),
        (constraints.audience, (grant.consumer_id,), "audience"),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise FreshEffectAuthorizationV1Error(
                f"effective authorization {label} scope is not exact for canonical request"
            )
    if constraints.delegation_depth != 0 or constraints.redelegation:
        raise FreshEffectAuthorizationV1Error(
            "effect execution authority must terminate delegation at the executing principal"
        )


def assert_fresh_effect_authorization_v1(
    *,
    authorization_ledger: AuthorizationStateLedgerV1,
    state: AuthorizationStateV1,
    delegation_chain: tuple[DelegationLinkV1, ...],
    intent: IntentCommitmentV1,
    grant: ExternalAdapterGrantV1,
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    current_epoch: int,
) -> ExecutionAuthorizationSnapshotV1:
    """Prove current, exact authority for one canonical effect request.

    The intent remains non-authoritative. It is required only to bind the
    authorization state to the exact sealed request (`intent_digest ==
    request.digest`). The current ledger head and delegation validity are then
    re-evaluated at the execution epoch by AuthorizationStateLedgerV1.
    """

    if not isinstance(authorization_ledger, AuthorizationStateLedgerV1):
        raise FreshEffectAuthorizationV1Error("authorization state ledger is required")
    mir.assert_sealed()
    request.assert_sealed(mir)
    if not isinstance(current_epoch, int) or isinstance(current_epoch, bool) or current_epoch < 0:
        raise FreshEffectAuthorizationV1Error("current_epoch must be a non-negative integer")
    if current_epoch != request.epoch:
        raise FreshEffectAuthorizationV1Error("execution epoch differs from canonical request")

    principal = canonical_execution_principal_v1(request)
    if intent.principal != principal:
        raise FreshEffectAuthorizationV1Error("intent principal differs from canonical request identity")
    if intent.intent_digest != request.digest:
        raise FreshEffectAuthorizationV1Error("intent is not bound to the exact canonical request")
    if intent.created_epoch > current_epoch:
        raise FreshEffectAuthorizationV1Error("intent was created after the execution epoch")
    if state.subject != principal:
        raise FreshEffectAuthorizationV1Error("authorization subject differs from canonical request identity")
    if state.intent_commitment_digest != intent.digest:
        raise FreshEffectAuthorizationV1Error("authorization state is bound to a different intent")
    if grant.subject_scope_digest != canonical_subject_scope_digest_v1(request):
        raise FreshEffectAuthorizationV1Error("adapter grant scope differs from canonical request")

    _assert_exact_effect_constraints(state, request=request, grant=grant)
    return authorization_ledger.snapshot_for_execution(
        state,
        delegation_chain,
        execution_epoch=current_epoch,
    )


def execute_effect_with_fresh_authorization_v1(
    *,
    authorization_ledger: AuthorizationStateLedgerV1,
    state: AuthorizationStateV1,
    delegation_chain: tuple[DelegationLinkV1, ...],
    intent: IntentCommitmentV1,
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
) -> tuple[
    ExecutionAuthorizationSnapshotV1,
    ExecutionConsumptionReceiptV1,
    EffectExecutionReceiptV1,
    bytes | None,
]:
    """Fresh-authority gate -> existing single-use permit -> measured effect.

    Any freshness, revocation, subject, intent or exact-scope failure occurs
    before the permit is consumed and before the effect callback can run.
    """

    snapshot = assert_fresh_effect_authorization_v1(
        authorization_ledger=authorization_ledger,
        state=state,
        delegation_chain=delegation_chain,
        intent=intent,
        grant=grant,
        mir=mir,
        request=request,
        current_epoch=current_epoch,
    )
    consumption, receipt, result = execute_effect_with_receipt_v1(
        ledger=ledger,
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
    return snapshot, consumption, receipt, result
