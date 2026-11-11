from dataclasses import replace
import hashlib
import unittest

from koschei.authorization_transition_v1 import (
    AuthorizationTransitionV1Error,
    ConstraintSetV1,
    DelegationLinkV1,
    IntentCommitmentV1,
    authorization_snapshot_for_execution_v1,
    issue_authorization_state_v1,
    transition_authorization_state_v1,
)


def dhex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def constraints(
    *,
    resources=("treasury", "reports"),
    operations=("read", "transfer"),
    arguments=("usd", "eur"),
    audience=("finance-agent", "ops-agent"),
    magnitude_max=100,
    valid_from_epoch=10,
    expires_before_epoch=30,
    delegation_depth=3,
    redelegation=True,
):
    return ConstraintSetV1(
        resources=resources,
        operations=operations,
        arguments=arguments,
        audience=audience,
        magnitude_max=magnitude_max,
        valid_from_epoch=valid_from_epoch,
        expires_before_epoch=expires_before_epoch,
        delegation_depth=delegation_depth,
        redelegation=redelegation,
    )


def link(
    delegation_id: str,
    *,
    issuer: str,
    subject: str,
    scope: ConstraintSetV1,
    checked_epoch: int,
    parent: DelegationLinkV1 | None = None,
    signature_valid=True,
    revocation_status="valid",
):
    return DelegationLinkV1(
        delegation_id=delegation_id,
        parent_delegation_id=None if parent is None else parent.delegation_id,
        issuer=issuer,
        subject=subject,
        constraints=scope,
        parent_commitment=None if parent is None else parent.authority_digest,
        checked_epoch=checked_epoch,
        signature_valid=signature_valid,
        revocation_status=revocation_status,
    )


def chain_at(epoch: int, *, parent_status="valid"):
    root = link(
        "root",
        issuer="human-owner",
        subject="agent-a",
        scope=constraints(),
        checked_epoch=epoch,
        revocation_status=parent_status,
    )
    child_scope = constraints(
        resources=("treasury",),
        operations=("transfer",),
        arguments=("usd",),
        audience=("finance-agent",),
        magnitude_max=50,
        valid_from_epoch=10,
        expires_before_epoch=25,
        delegation_depth=2,
        redelegation=True,
    )
    child = link(
        "child",
        issuer="agent-a",
        subject="agent-b",
        scope=child_scope,
        checked_epoch=epoch,
        parent=root,
    )
    return root, child


def intent() -> IntentCommitmentV1:
    return IntentCommitmentV1(
        principal="agent-b",
        intent_digest=dhex("intent"),
        purpose_digest=dhex("purpose"),
        created_epoch=10,
    )


class AuthorizationTransitionV1Tests(unittest.TestCase):
    def test_intent_commitment_is_context_not_authority(self):
        committed = intent()
        self.assertFalse(committed.authority)
        self.assertNotEqual(committed.digest, committed.intent_digest)

    def test_valid_delegation_can_issue_and_refresh_execution_snapshot(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        snapshot = authorization_snapshot_for_execution_v1(
            state,
            chain_at(18),
            execution_epoch=18,
        )
        self.assertFalse(snapshot.authority)
        self.assertEqual(snapshot.state_digest, state.state_digest)
        self.assertEqual(snapshot.execution_epoch, 18)

    def test_was_valid_parent_is_not_valid_parent_now(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "revocation state"):
            authorization_snapshot_for_execution_v1(
                state,
                chain_at(18, parent_status="revoked"),
                execution_epoch=18,
            )

    def test_stale_parent_check_fails_closed_at_execution(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "stale"):
            authorization_snapshot_for_execution_v1(
                state,
                chain_at(12),
                execution_epoch=18,
            )

    def test_constraint_lattice_rejects_widening_on_every_axis(self):
        cases = (
            ("resources", ("treasury", "reports", "admin"), "resources broadens"),
            ("operations", ("read", "transfer", "delete"), "operations broadens"),
            ("arguments", ("usd", "eur", "secret"), "arguments broadens"),
            ("audience", ("finance-agent", "ops-agent", "unknown"), "audience broadens"),
            ("magnitude_max", 101, "magnitude broadens"),
            ("valid_from_epoch", 9, "validity start broadens"),
            ("expires_before_epoch", 31, "validity end broadens"),
            ("delegation_depth", 4, "delegation_depth broadens"),
        )
        parent = constraints()
        for field, value, error in cases:
            with self.subTest(field=field):
                child = replace(parent, **{field: value})
                with self.assertRaisesRegex(AuthorizationTransitionV1Error, error):
                    child.assert_attenuates(parent)

    def test_redelegation_cannot_be_reenabled(self):
        parent = constraints(redelegation=False)
        child = replace(parent, redelegation=True)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "redelegation broadens"):
            child.assert_attenuates(parent)

    def test_delegation_hop_consumes_depth_and_requires_parent_redelegation(self):
        parent = constraints(delegation_depth=2)
        replace(parent, delegation_depth=1).assert_attenuates(parent, delegation_hop=True)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "consume delegation depth"):
            replace(parent, delegation_depth=2).assert_attenuates(parent, delegation_hop=True)
        disabled = replace(parent, redelegation=False)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "does not permit"):
            replace(disabled, delegation_depth=1).assert_attenuates(
                disabled,
                delegation_hop=True,
            )

    def test_narrow_then_step_up_never_exceeds_immutable_ceiling(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        narrowed = replace(
            state.effective_constraints,
            magnitude_max=20,
            delegation_depth=1,
            redelegation=False,
        )
        state, narrow_transition = transition_authorization_state_v1(
            state,
            kind="NARROW",
            epoch=13,
            reason_digest=dhex("budget-reduced"),
            next_effective_constraints=narrowed,
        )
        self.assertEqual(narrow_transition.kind, "NARROW")
        self.assertEqual(state.effective_constraints.magnitude_max, 20)

        restored = replace(state.authority_ceiling, magnitude_max=40)
        state, step_up = transition_authorization_state_v1(
            state,
            kind="STEP_UP",
            epoch=14,
            reason_digest=dhex("fresh-approval"),
            next_effective_constraints=restored,
        )
        self.assertEqual(step_up.kind, "STEP_UP")
        self.assertEqual(state.effective_constraints.magnitude_max, 40)

        too_broad = replace(state.authority_ceiling, magnitude_max=60)
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "magnitude broadens"):
            transition_authorization_state_v1(
                state,
                kind="STEP_UP",
                epoch=15,
                reason_digest=dhex("bad-step-up"),
                next_effective_constraints=too_broad,
            )

    def test_revocation_after_initial_authorization_denies_execution_snapshot(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        state, transition = transition_authorization_state_v1(
            state,
            kind="REVOKE",
            epoch=17,
            reason_digest=dhex("owner-revoked"),
        )
        self.assertEqual(transition.kind, "REVOKE")
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "not active"):
            authorization_snapshot_for_execution_v1(
                state,
                chain_at(18),
                execution_epoch=18,
            )

    def test_terminal_and_suspended_states_cannot_silently_recover(self):
        state = issue_authorization_state_v1(intent(), chain_at(12), epoch=12)
        suspended, _ = transition_authorization_state_v1(
            state,
            kind="SUSPEND",
            epoch=13,
            reason_digest=dhex("approval-withdrawn"),
        )
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "silently recover"):
            transition_authorization_state_v1(
                suspended,
                kind="STEP_UP",
                epoch=14,
                reason_digest=dhex("implicit-recovery"),
                next_effective_constraints=suspended.authority_ceiling,
            )

        revoked, _ = transition_authorization_state_v1(
            suspended,
            kind="REVOKE",
            epoch=14,
            reason_digest=dhex("final-revoke"),
        )
        with self.assertRaisesRegex(AuthorizationTransitionV1Error, "terminal"):
            transition_authorization_state_v1(
                revoked,
                kind="NARROW",
                epoch=15,
                reason_digest=dhex("impossible"),
                next_effective_constraints=revoked.effective_constraints,
            )


if __name__ == "__main__":
    unittest.main()
