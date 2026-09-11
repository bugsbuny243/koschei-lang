from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from koschei.authorization_decision_v1 import issue_authorization_decision_v1
from koschei.authorization_transition_v1 import (
    ConstraintSetV1,
    DelegationLinkV1,
    IntentCommitmentV1,
    issue_authorization_state_v1,
    transition_authorization_state_v1,
)
from koschei.canonical_authority_basis_v1 import (
    canonical_subject_scope_digest_v1,
    derive_canonical_authority_basis_v1,
)
from koschei.durable_authorization_store_v1 import (
    DurableAuthorizationStoreV1,
    DurableAuthorizationStoreV1Error,
)
from koschei.durable_effect_execution_v1 import (
    DurableEffectExecutionV1Error,
    execute_effect_with_durable_authorization_v1,
)
from koschei.execution_permit_v1 import mint_execution_permit_v1
from koschei.external_adapter_contract_v1 import (
    admit_external_adapter_evidence_v1,
    issue_external_adapter_grant_v1,
)
from koschei.fresh_effect_authorization_v1 import canonical_execution_principal_v1
from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_request_binding_v1 import bind_proof_to_request, seal_effect_request
from koschei.parser import parse

SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def h(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def effect_chain():
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir).library_plan
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=hashlib.sha256(step.binding_digest.encode()).hexdigest(),
            success=True,
        )
        for step in plan.steps
    ]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir,
        effect_id="pi-subscription-41",
        subject="withdrawal",
        operation="subscription.enable",
        request_digest=h("payload"),
        identity_digest=h("pi-user-41"),
        epoch=41,
        nonce_digest=h("nonce"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    basis = derive_canonical_authority_basis_v1(
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
    )
    grant = issue_external_adapter_grant_v1(
        provider_id="pi",
        consumer_id="koschei-lab-pi",
        subject_scope_digest=canonical_subject_scope_digest_v1(request),
        allowed_actions=("payment.observe",),
        valid_from_epoch=41,
        expires_before_epoch=42,
    )
    evidence = admit_external_adapter_evidence_v1(
        grant,
        action="payment.observe",
        external_evidence_digest=h("settled-payment"),
        observed_epoch=41,
    )
    decision_key = b"d" * 32
    runtime_key = b"r" * 32
    effect_key = b"e" * 32
    claim_key = b"c" * 32
    decision = issue_authorization_decision_v1(
        grant,
        evidence,
        basis,
        mir=mir,
        request=request,
        proof=proof,
        bound=bound,
        decision_key=decision_key,
    )
    permit = mint_execution_permit_v1(
        grant,
        evidence,
        decision,
        runtime_key=runtime_key,
        decision_key=decision_key,
    )
    return locals()


def authority(items):
    request = items["request"]
    grant = items["grant"]
    principal = canonical_execution_principal_v1(request)
    intent = IntentCommitmentV1(
        principal=principal,
        intent_digest=request.digest,
        purpose_digest=h("enable-paid-subscription"),
        created_epoch=41,
    )
    constraints = ConstraintSetV1(
        resources=(request.subject,),
        operations=(request.operation,),
        arguments=(request.request_digest,),
        audience=(grant.consumer_id,),
        magnitude_max=None,
        valid_from_epoch=41,
        expires_before_epoch=42,
        delegation_depth=0,
        redelegation=False,
    )
    delegation_chain = (
        DelegationLinkV1(
            delegation_id="effect-root",
            parent_delegation_id=None,
            issuer="human-owner",
            subject=principal,
            constraints=constraints,
            parent_commitment=None,
            checked_epoch=41,
            signature_valid=True,
            revocation_status="valid",
        ),
    )
    state = issue_authorization_state_v1(intent, delegation_chain, epoch=41)
    return intent, delegation_chain, state


def claim_kwargs(items, state, delegation_chain, intent=None):
    return dict(
        state=state,
        delegation_chain=delegation_chain,
        intent=intent or authority(items)[0],
        permit=items["permit"],
        runtime_key=items["runtime_key"],
        decision_key=items["decision_key"],
        grant=items["grant"],
        evidence=items["evidence"],
        decision=items["decision"],
        mir=items["mir"],
        request=items["request"],
        current_epoch=41,
        claim_key=items["claim_key"],
    )


def execute_kwargs(items, store, intent, delegation_chain, state, effect):
    return dict(
        store=store,
        state=state,
        delegation_chain=delegation_chain,
        intent=intent,
        permit=items["permit"],
        runtime_key=items["runtime_key"],
        decision_key=items["decision_key"],
        claim_key=items["claim_key"],
        effect_key=items["effect_key"],
        grant=items["grant"],
        evidence=items["evidence"],
        decision=items["decision"],
        mir=items["mir"],
        request=items["request"],
        current_epoch=41,
        effect=effect,
    )


class DurableAuthorizationStoreV1Tests(unittest.TestCase):
    """Dependency-free durable replay/revocation acceptance candidates."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_initial_head_and_claim_survive_reopen(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        path = self.tmp_path / "authority.db"
        store = DurableAuthorizationStoreV1(path)
        store.register_initial(state)
        snapshot, claim = store.claim_execution(
            **claim_kwargs(items, state, delegation_chain, intent)
        )

        reopened = DurableAuthorizationStoreV1(path)
        self.assertEqual(reopened.current_head_digest(state.subject), state.state_digest)
        self.assertTrue(reopened.has_execution_claim(items["permit"].permit_digest))
        claim.assert_authenticated(
            claim_key=items["claim_key"],
            state=state,
            snapshot=snapshot,
            permit=items["permit"],
        )
        with self.assertRaisesRegex(DurableAuthorizationStoreV1Error, "replay detected"):
            reopened.claim_execution(**claim_kwargs(items, state, delegation_chain, intent))

    def test_durable_revocation_head_blocks_old_state_claim(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        store = DurableAuthorizationStoreV1(self.tmp_path / "authority.db")
        store.register_initial(state)
        revoked, transition = transition_authorization_state_v1(
            state,
            kind="REVOKE",
            epoch=42,
            reason_digest=h("owner-revoked"),
        )
        store.commit_transition(state, revoked, transition)

        with self.assertRaisesRegex(
            DurableAuthorizationStoreV1Error, "current durable monotonic head"
        ):
            store.claim_execution(**claim_kwargs(items, state, delegation_chain, intent))
        self.assertFalse(store.has_execution_claim(items["permit"].permit_digest))

    def test_transition_head_persists_and_stale_compare_and_swap_fails(self):
        items = effect_chain()
        _, _, state = authority(items)
        path = self.tmp_path / "authority.db"
        store = DurableAuthorizationStoreV1(path)
        store.register_initial(state)
        revoked, transition = transition_authorization_state_v1(
            state,
            kind="REVOKE",
            epoch=42,
            reason_digest=h("owner-revoked"),
        )
        store.commit_transition(state, revoked, transition)
        reopened = DurableAuthorizationStoreV1(path)
        self.assertEqual(reopened.current_head_digest(state.subject), revoked.state_digest)
        with self.assertRaisesRegex(
            DurableAuthorizationStoreV1Error, "current durable monotonic head"
        ):
            reopened.commit_transition(state, revoked, transition)

    def test_concurrent_duplicate_claim_has_exactly_one_local_winner(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        path = self.tmp_path / "authority.db"
        DurableAuthorizationStoreV1(path).register_initial(state)

        def contender():
            store = DurableAuthorizationStoreV1(path)
            try:
                store.claim_execution(**claim_kwargs(items, state, delegation_chain, intent))
                return "claimed"
            except DurableAuthorizationStoreV1Error as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: contender(), range(2)))
        self.assertEqual(outcomes.count("claimed"), 1)
        self.assertEqual(sum("replay detected" in item for item in outcomes), 1)

    def test_durable_executor_commits_claim_before_callback_and_blocks_restart_replay(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        path = self.tmp_path / "authority.db"
        store = DurableAuthorizationStoreV1(path)
        store.register_initial(state)
        calls = []

        snapshot, claim, consumption, receipt, result = execute_effect_with_durable_authorization_v1(
            **execute_kwargs(
                items,
                store,
                intent,
                delegation_chain,
                state,
                lambda _: calls.append(
                    store.has_execution_claim(items["permit"].permit_digest)
                )
                or b"ok",
            )
        )
        self.assertEqual(calls, [True])
        self.assertEqual(result, b"ok")
        self.assertEqual(receipt.outcome, "effect-completed")
        self.assertEqual(consumption.permit_digest, items["permit"].permit_digest)
        claim.assert_authenticated(
            claim_key=items["claim_key"], state=state, snapshot=snapshot, permit=items["permit"]
        )

        replay_calls = []
        reopened = DurableAuthorizationStoreV1(path)
        with self.assertRaisesRegex(DurableAuthorizationStoreV1Error, "replay detected"):
            execute_effect_with_durable_authorization_v1(
                **execute_kwargs(
                    items,
                    reopened,
                    intent,
                    delegation_chain,
                    state,
                    lambda _: replay_calls.append(1) or b"bad",
                )
            )
        self.assertEqual(replay_calls, [])

    def test_invalid_effect_key_does_not_burn_durable_claim(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        store = DurableAuthorizationStoreV1(self.tmp_path / "authority.db")
        store.register_initial(state)
        calls = []
        kwargs = execute_kwargs(
            items,
            store,
            intent,
            delegation_chain,
            state,
            lambda _: calls.append(1) or b"bad",
        )
        kwargs["effect_key"] = b"short"
        with self.assertRaisesRegex(DurableEffectExecutionV1Error, "effect_key"):
            execute_effect_with_durable_authorization_v1(**kwargs)
        self.assertFalse(store.has_execution_claim(items["permit"].permit_digest))
        self.assertEqual(calls, [])

    def test_direct_durable_claim_cannot_bypass_exact_intent_binding(self):
        items = effect_chain()
        intent, delegation_chain, state = authority(items)
        store = DurableAuthorizationStoreV1(self.tmp_path / "authority.db")
        store.register_initial(state)
        forged_intent = IntentCommitmentV1(
            principal=intent.principal,
            intent_digest=h("different-request"),
            purpose_digest=intent.purpose_digest,
            created_epoch=41,
        )
        with self.assertRaisesRegex(ValueError, "exact canonical request"):
            store.claim_execution(
                **claim_kwargs(items, state, delegation_chain, forged_intent)
            )
        self.assertFalse(store.has_execution_claim(items["permit"].permit_digest))

    def test_schema_version_mismatch_fails_closed(self):
        path = self.tmp_path / "authority.db"
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE koschei_store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO koschei_store_metadata(key, value) VALUES('schema_version', '999')"
        )
        conn.commit()
        conn.close()

        with self.assertRaisesRegex(
            DurableAuthorizationStoreV1Error, "unsupported.*schema version"
        ):
            DurableAuthorizationStoreV1(path)

    def test_directory_path_is_rejected_fail_closed(self):
        with self.assertRaisesRegex(DurableAuthorizationStoreV1Error, "not a file"):
            DurableAuthorizationStoreV1(self.tmp_path)


if __name__ == "__main__":
    unittest.main()
