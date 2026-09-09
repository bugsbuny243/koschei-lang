import hashlib

import pytest

from koschei.authorization_state_ledger_v1 import AuthorizationStateLedgerV1
from koschei.authorization_transition_v1 import (
    AuthorizationTransitionV1Error,
    ConstraintSetV1,
    DelegationLinkV1,
    IntentCommitmentV1,
    issue_authorization_state_v1,
    transition_authorization_state_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def scope() -> ConstraintSetV1:
    return ConstraintSetV1(
        resources=("treasury",),
        operations=("transfer",),
        arguments=("usd",),
        audience=("finance-agent",),
        magnitude_max=50,
        valid_from_epoch=10,
        expires_before_epoch=30,
        delegation_depth=1,
        redelegation=False,
    )


def chain(epoch: int) -> tuple[DelegationLinkV1, ...]:
    return (
        DelegationLinkV1(
            delegation_id="root",
            parent_delegation_id=None,
            issuer="human-owner",
            subject="agent-a",
            constraints=scope(),
            parent_commitment=None,
            checked_epoch=epoch,
            signature_valid=True,
            revocation_status="valid",
        ),
    )


def initial_state():
    intent = IntentCommitmentV1(
        principal="agent-a",
        intent_digest=dhex("intent"),
        purpose_digest=dhex("purpose"),
        created_epoch=10,
    )
    return issue_authorization_state_v1(intent, chain(12), epoch=12)


def test_current_head_can_create_fresh_execution_snapshot():
    state = initial_state()
    ledger = AuthorizationStateLedgerV1()
    ledger.register_initial(state)
    snapshot = ledger.snapshot_for_execution(state, chain(12), execution_epoch=12)
    assert snapshot.state_digest == state.state_digest


def test_revocation_advances_head_and_rejects_old_active_state_rollback():
    active = initial_state()
    ledger = AuthorizationStateLedgerV1()
    ledger.register_initial(active)
    revoked, transition = transition_authorization_state_v1(
        active,
        kind="REVOKE",
        epoch=13,
        reason_digest=dhex("owner-revoked"),
    )
    ledger.commit_transition(active, revoked, transition)

    with pytest.raises(AuthorizationTransitionV1Error, match="current monotonic head"):
        ledger.snapshot_for_execution(active, chain(14), execution_epoch=14)
    with pytest.raises(AuthorizationTransitionV1Error, match="not active"):
        ledger.snapshot_for_execution(revoked, chain(14), execution_epoch=14)


def test_transition_commit_must_extend_current_head():
    active = initial_state()
    ledger = AuthorizationStateLedgerV1()
    ledger.register_initial(active)
    narrowed, transition = transition_authorization_state_v1(
        active,
        kind="NARROW",
        epoch=13,
        reason_digest=dhex("budget-reduced"),
        next_effective_constraints=ConstraintSetV1(
            resources=("treasury",),
            operations=("transfer",),
            arguments=("usd",),
            audience=("finance-agent",),
            magnitude_max=20,
            valid_from_epoch=10,
            expires_before_epoch=30,
            delegation_depth=0,
            redelegation=False,
        ),
    )
    ledger.commit_transition(active, narrowed, transition)
    with pytest.raises(AuthorizationTransitionV1Error, match="current monotonic head"):
        ledger.commit_transition(active, narrowed, transition)


def test_unregistered_state_fails_closed():
    with pytest.raises(AuthorizationTransitionV1Error, match="head is unavailable"):
        AuthorizationStateLedgerV1().snapshot_for_execution(
            initial_state(),
            chain(12),
            execution_epoch=12,
        )
