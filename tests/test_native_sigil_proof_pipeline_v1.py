from __future__ import annotations

from dataclasses import replace
import unittest

from koschei.library_proof_envelope_v1 import LibraryProofError, make_receipt
from koschei.native_sigil_library_bridge_v1 import expand_native_sigil_mir
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_proof_pipeline_v1 import (
    NativeSigilProofPipelineError,
    require_native_sigil_proof,
    seal_native_sigil_proof,
)
from koschei.parser import parse


SOURCE = """
ka treasury;
vor withdrawal;
shi evidence;
thal recovery;
nur visibility;
"""


def _mir():
    return lower_native_sigils(parse(SOURCE))


def _successful_receipts(mir):
    plan = expand_native_sigil_mir(mir)
    return tuple(
        make_receipt(
            activation_step_id=step.activation_step_id,
            obligation=step.obligation,
            subsystem=step.subsystem,
            proof_kind=step.proof_kind,
            evidence_digest=f"evidence:{index}:{step.binding_digest}",
            success=True,
        )
        for index, step in enumerate(plan.library_plan.steps)
    )


class NativeSigilProofPipelineTests(unittest.TestCase):
    def test_real_source_reaches_allow_proof_bundle(self) -> None:
        mir = _mir()
        bundle = seal_native_sigil_proof(mir, _successful_receipts(mir))
        self.assertEqual(bundle.decision, "ALLOW")
        plan = require_native_sigil_proof(mir, bundle)
        self.assertEqual(bundle.native_mir_fingerprint, mir.fingerprint)
        self.assertEqual(bundle.native_library_plan_digest, plan.digest)

    def test_failed_library_obligation_never_becomes_allow(self) -> None:
        mir = _mir()
        receipts = list(_successful_receipts(mir))
        failed = receipts[-1]
        receipts[-1] = make_receipt(
            activation_step_id=failed.activation_step_id,
            obligation=failed.obligation,
            subsystem=failed.subsystem,
            proof_kind=failed.proof_kind,
            evidence_digest=failed.evidence_digest,
            success=False,
        )
        bundle = seal_native_sigil_proof(mir, receipts)
        self.assertEqual(bundle.decision, "DENY")

    def test_missing_receipt_fails_closed(self) -> None:
        mir = _mir()
        receipts = _successful_receipts(mir)
        with self.assertRaises(LibraryProofError):
            seal_native_sigil_proof(mir, receipts[:-1])

    def test_bundle_cannot_be_rebound_to_other_compiler_product(self) -> None:
        mir = _mir()
        bundle = seal_native_sigil_proof(mir, _successful_receipts(mir))
        other = lower_native_sigils(parse("ka vault;\nvor withdrawal;\nshi evidence;\nthal recovery;\nnur visibility;"))
        with self.assertRaises(NativeSigilProofPipelineError):
            require_native_sigil_proof(other, bundle)

    def test_decision_tampering_is_rejected(self) -> None:
        mir = _mir()
        bundle = seal_native_sigil_proof(mir, _successful_receipts(mir))
        tampered = replace(bundle, decision="DENY")
        with self.assertRaises(NativeSigilProofPipelineError):
            require_native_sigil_proof(mir, tampered)

    def test_pipeline_is_deterministic_for_same_evidence(self) -> None:
        mir = _mir()
        receipts = _successful_receipts(mir)
        first = seal_native_sigil_proof(mir, receipts)
        second = seal_native_sigil_proof(mir, receipts)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.library_proof.digest, second.library_proof.digest)


if __name__ == "__main__":
    unittest.main()
