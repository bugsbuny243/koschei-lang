from __future__ import annotations

import hashlib
import unittest

from koschei.library_proof_envelope_v1 import make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import seal_native_sigil_proof
from koschei.native_sigil_replay_ledger_v1 import (
    NativeSigilReplayError,
    ReplayLedger,
    enforce_once,
)
from koschei.native_sigil_request_binding_v1 import (
    bind_proof_to_request,
    seal_effect_request,
)
from koschei.parser import parse


SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def _evidence(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _fixture(*, fail_obligation: str | None = None):
    program = parse(SOURCE)
    mir = lower_native_sigils(program)
    plan = expand_native_sigil_mir(mir)
    receipts = [
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=_evidence(step.obligation),
            success=step.obligation != fail_obligation,
        )
        for step in plan.library_plan.steps
    ]
    proof = seal_native_sigil_proof(mir, receipts)
    request = seal_effect_request(
        mir,
        effect_id="withdrawal:42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=_evidence("payload:42"),
        identity_digest=_evidence("operator:7"),
        epoch=7,
        nonce_digest=_evidence("nonce:42"),
    )
    bound = bind_proof_to_request(mir, request, proof)
    return mir, proof, request, bound


class NativeSigilReplayLedgerTests(unittest.TestCase):
    def test_allow_executes_once_and_commits(self) -> None:
        mir, proof, request, bound = _fixture()
        ledger = ReplayLedger()
        calls: list[str] = []

        decision, value, record = enforce_once(
            ledger,
            mir,
            request,
            proof,
            bound,
            lambda item: calls.append(item.effect_id) or "signed",
        )

        self.assertEqual(decision.decision, "ALLOW")
        self.assertEqual(value, "signed")
        self.assertEqual(calls, ["withdrawal:42"])
        self.assertEqual(record.state, "COMMITTED")

        with self.assertRaises(NativeSigilReplayError):
            enforce_once(
                ledger,
                mir,
                request,
                proof,
                bound,
                lambda item: calls.append(item.effect_id),
            )
        self.assertEqual(calls, ["withdrawal:42"])

    def test_denied_request_is_consumed(self) -> None:
        mir, proof, request, bound = _fixture(fail_obligation="derive-least-authority")
        ledger = ReplayLedger()
        calls: list[str] = []

        decision, value, record = enforce_once(
            ledger, mir, request, proof, bound, lambda item: calls.append(item.effect_id)
        )
        self.assertEqual(decision.decision, "DENY")
        self.assertIsNone(value)
        self.assertEqual(calls, [])
        self.assertEqual(record.state, "REJECTED")

        with self.assertRaises(NativeSigilReplayError):
            enforce_once(ledger, mir, request, proof, bound, lambda item: None)

    def test_contained_request_is_consumed(self) -> None:
        mir, proof, request, bound = _fixture(fail_obligation="fence-stale-writers")
        ledger = ReplayLedger()
        decision, value, record = enforce_once(
            ledger, mir, request, proof, bound, lambda item: "must-not-run"
        )
        self.assertEqual(decision.decision, "CONTAIN")
        self.assertIsNone(value)
        self.assertEqual(record.state, "CONTAINED")

    def test_effect_exception_tombstones_request_as_uncertain(self) -> None:
        mir, proof, request, bound = _fixture()
        ledger = ReplayLedger()
        calls = 0

        def explode(_):
            nonlocal calls
            calls += 1
            raise RuntimeError("transport lost after send")

        with self.assertRaises(NativeSigilReplayError):
            enforce_once(ledger, mir, request, proof, bound, explode)

        self.assertEqual(calls, 1)
        record = ledger.get(request.digest)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.state, "UNCERTAIN")

        with self.assertRaises(NativeSigilReplayError):
            enforce_once(ledger, mir, request, proof, bound, lambda item: "retry")


if __name__ == "__main__":
    unittest.main()
