from __future__ import annotations

import unittest

from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_enforcement_gate_v1 import (
    PrivilegedEffectIntent,
    enforce_effect,
    evaluate_enforcement,
)
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.parser import parse


SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def _mir_and_plan():
    mir = lower_native_sigils(parse(SOURCE))
    plan = expand_native_sigil_mir(mir)
    return mir, plan


def _receipts(plan, failed_obligation: str | None = None):
    return tuple(
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=f"evidence:{step.binding_digest}",
            success=step.obligation != failed_obligation,
        )
        for step in plan.library_plan.steps
    )


class NativeSigilEnforcementGateTests(unittest.TestCase):
    def test_allow_executes_effect_once(self) -> None:
        mir, plan = _mir_and_plan()
        proof = seal_native_sigil_proof(mir, _receipts(plan))
        intent = PrivilegedEffectIntent(
            effect_id="withdrawal:42",
            subject="withdrawal",
            operation="signer.execute",
            request_digest="request-digest-42",
        )
        calls = []

        decision, value = enforce_effect(
            mir,
            proof,
            intent,
            lambda item: calls.append(item.effect_id) or "signed",
        )

        self.assertEqual(decision.decision, "ALLOW")
        self.assertEqual(value, "signed")
        self.assertEqual(calls, ["withdrawal:42"])
        decision.assert_sealed()

    def test_non_containment_failure_denies_without_effect(self) -> None:
        mir, plan = _mir_and_plan()
        proof = seal_native_sigil_proof(
            mir,
            _receipts(plan, "derive-least-authority"),
        )
        intent = PrivilegedEffectIntent(
            "withdrawal:43", "withdrawal", "signer.execute", "request-digest-43"
        )
        calls = []

        decision, value = enforce_effect(
            mir,
            proof,
            intent,
            lambda item: calls.append(item.effect_id),
        )

        self.assertEqual(decision.decision, "DENY")
        self.assertIsNone(value)
        self.assertEqual(calls, [])
        self.assertIn("derive-least-authority", decision.failed_obligations)

    def test_containment_failure_contains_without_effect(self) -> None:
        mir, plan = _mir_and_plan()
        proof = seal_native_sigil_proof(
            mir,
            _receipts(plan, "fence-stale-writers"),
        )
        intent = PrivilegedEffectIntent(
            "withdrawal:44", "withdrawal", "signer.execute", "request-digest-44"
        )
        calls = []

        decision, value = enforce_effect(
            mir,
            proof,
            intent,
            lambda item: calls.append(item.effect_id),
        )

        self.assertEqual(decision.decision, "CONTAIN")
        self.assertIsNone(value)
        self.assertEqual(calls, [])
        self.assertIn("fence-stale-writers", decision.failed_obligations)

    def test_decision_is_deterministic_for_same_inputs(self) -> None:
        mir, plan = _mir_and_plan()
        proof = seal_native_sigil_proof(mir, _receipts(plan))
        intent = PrivilegedEffectIntent(
            "withdrawal:45", "withdrawal", "signer.execute", "request-digest-45"
        )

        first = evaluate_enforcement(mir, proof, intent)
        second = evaluate_enforcement(mir, proof, intent)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
