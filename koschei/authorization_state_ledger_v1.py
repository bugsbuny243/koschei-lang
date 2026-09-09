"""Monotonic current-state head for time-evolving Koschei authorization v1.

A transition hash chain alone cannot prove that a presented active state is the
latest state.  This bootstrap ledger prevents rollback to an older active state
inside one trusted runtime.  Production use requires durable/shared monotonic
state; this in-memory implementation deliberately does not claim that property.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .authorization_transition_v1 import (
    AuthorizationStateV1,
    AuthorizationTransitionV1,
    AuthorizationTransitionV1Error,
    DelegationLinkV1,
    ExecutionAuthorizationSnapshotV1,
    _hash,
    _state_digest,
    authorization_snapshot_for_execution_v1,
)


@dataclass(slots=True)
class AuthorizationStateLedgerV1:
    """Bootstrap monotonic state head keyed by authorization subject."""

    heads: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _assert_sealed(state: AuthorizationStateV1) -> None:
        expected = _state_digest(replace(state, state_digest=""))
        if expected != state.state_digest:
            raise AuthorizationTransitionV1Error("authorization state seal mismatch")

    @staticmethod
    def _assert_transition_sealed(transition: AuthorizationTransitionV1) -> None:
        payload = {
            "kind": transition.kind,
            "epoch": transition.epoch,
            "previous_state_digest": transition.previous_state_digest,
            "next_state_digest": transition.next_state_digest,
            "reason_digest": transition.reason_digest,
            "version": transition.version,
        }
        expected = _hash(b"koschei.authorization-transition/v1", payload)
        if expected != transition.transition_digest:
            raise AuthorizationTransitionV1Error("authorization transition seal mismatch")

    def register_initial(self, state: AuthorizationStateV1) -> None:
        self._assert_sealed(state)
        if state.previous_state_digest is not None:
            raise AuthorizationTransitionV1Error("initial authorization state cannot have a predecessor")
        if state.status != "active":
            raise AuthorizationTransitionV1Error("initial authorization state must be active")
        if state.subject in self.heads:
            raise AuthorizationTransitionV1Error("authorization state head already exists")
        self.heads[state.subject] = state.state_digest

    def assert_current(self, state: AuthorizationStateV1) -> None:
        self._assert_sealed(state)
        head = self.heads.get(state.subject)
        if head is None:
            raise AuthorizationTransitionV1Error("authorization state head is unavailable")
        if head != state.state_digest:
            raise AuthorizationTransitionV1Error("authorization state is not the current monotonic head")

    def commit_transition(
        self,
        previous: AuthorizationStateV1,
        next_state: AuthorizationStateV1,
        transition: AuthorizationTransitionV1,
    ) -> None:
        self.assert_current(previous)
        self._assert_sealed(next_state)
        self._assert_transition_sealed(transition)
        if previous.subject != next_state.subject:
            raise AuthorizationTransitionV1Error("authorization transition changes subject")
        if next_state.previous_state_digest != previous.state_digest:
            raise AuthorizationTransitionV1Error("next authorization state predecessor mismatch")
        if transition.previous_state_digest != previous.state_digest:
            raise AuthorizationTransitionV1Error("authorization transition previous-state mismatch")
        if transition.next_state_digest != next_state.state_digest:
            raise AuthorizationTransitionV1Error("authorization transition next-state mismatch")
        if transition.epoch != next_state.epoch:
            raise AuthorizationTransitionV1Error("authorization transition epoch mismatch")
        self.heads[previous.subject] = next_state.state_digest

    def snapshot_for_execution(
        self,
        state: AuthorizationStateV1,
        chain: tuple[DelegationLinkV1, ...],
        *,
        execution_epoch: int,
    ) -> ExecutionAuthorizationSnapshotV1:
        """Reject historical state rollback before fresh delegation verification."""
        self.assert_current(state)
        return authorization_snapshot_for_execution_v1(
            state,
            chain,
            execution_epoch=execution_epoch,
        )
