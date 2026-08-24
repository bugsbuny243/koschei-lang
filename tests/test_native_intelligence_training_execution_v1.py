from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_execution_v1 import (
    NativeTrainingExecutionError,
    build_native_intelligence_from_execution_receipt_v1,
    seal_native_training_execution_receipt_v1,
    seal_native_training_run_start_v1,
)
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_launch_v1 import seal_native_training_launch_v1
from koschei.native_intelligence_training_lineage_v1 import (
    seal_native_training_plan_v1,
    seal_native_training_receipt_v1,
)
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingExecutionV1Tests(unittest.TestCase):
    def setUp(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        self.holdout = build_native_intelligence_holdout_v1(curriculum)
        self.corpus = build_balanced_native_training_corpus_v1(
            self.holdout,
            variants_per_family=1,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.release = Path(self.temp.name) / "release"
        self.manifest = write_native_training_export_v1(
            self.holdout,
            self.corpus,
            self.release,
        )
        self.plan = seal_native_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            base_model_revision="1" * 40,
            base_weights_digest="2" * 64,
            training_config_digest="3" * 64,
            training_method="lora-sft-v1",
        )
        self.launch = seal_native_training_launch_v1(
            self.plan,
            self.manifest,
            self.release,
            trainer_environment_digest="4" * 64,
            launcher_digest="5" * 64,
        )
        self.run_start = seal_native_training_run_start_v1(
            self.plan,
            self.launch,
            self.manifest,
            provider="hf-jobs",
            job_reference_digest="6" * 64,
            start_evidence_digest="7" * 64,
        )
        self.artifact_receipt = seal_native_training_receipt_v1(
            self.plan,
            adapter_digest="8" * 64,
            final_checkpoint_digest="9" * 64,
            trainer_log_digest="a" * 64,
            completed_steps=123,
            completion_evidence_digest="b" * 64,
        )
        self.execution_receipt = seal_native_training_execution_receipt_v1(
            self.plan,
            self.launch,
            self.manifest,
            self.run_start,
            self.artifact_receipt,
        )

    def test_run_start_binds_exact_launch_environment_and_external_job_evidence(self):
        self.run_start.assert_for(self.plan, self.launch, self.manifest)
        self.assertEqual(self.run_start.plan_digest, self.plan.digest)
        self.assertEqual(self.run_start.launch_digest, self.launch.digest)
        self.assertEqual(
            self.run_start.trainer_environment_digest,
            self.launch.trainer_environment_digest,
        )
        self.assertEqual(self.run_start.launcher_digest, self.launch.launcher_digest)
        self.assertEqual(self.run_start.provider, "hf-jobs")
        self.assertFalse(self.run_start.authority)

    def test_run_start_cannot_be_rebound_to_another_launch(self):
        foreign_launch = replace(self.launch, launcher_digest="c" * 64)
        with self.assertRaises(NativeTrainingExecutionError):
            self.run_start.assert_for(self.plan, foreign_launch, self.manifest)

    def test_execution_receipt_binds_final_artifacts_to_exact_run_start(self):
        self.execution_receipt.assert_for(
            self.plan,
            self.launch,
            self.manifest,
            self.run_start,
            self.artifact_receipt,
        )
        self.assertEqual(
            self.execution_receipt.artifact_receipt_digest,
            self.artifact_receipt.digest,
        )
        self.assertEqual(
            self.execution_receipt.adapter_digest,
            self.artifact_receipt.adapter_digest,
        )
        self.assertFalse(self.execution_receipt.authority)
        self.assertFalse(self.execution_receipt.deployment_approved)

    def test_execution_receipt_rejects_foreign_run_or_artifact_receipt(self):
        foreign_start = replace(self.run_start, digest="d" * 64)
        with self.assertRaises(NativeTrainingExecutionError):
            self.execution_receipt.assert_for(
                self.plan,
                self.launch,
                self.manifest,
                foreign_start,
                self.artifact_receipt,
            )

        foreign_artifact = replace(self.artifact_receipt, digest="e" * 64)
        with self.assertRaises(NativeTrainingExecutionError):
            self.execution_receipt.assert_for(
                self.plan,
                self.launch,
                self.manifest,
                self.run_start,
                foreign_artifact,
            )

    def test_model_identity_uses_execution_receipt_as_training_run_identity(self):
        identity = build_native_intelligence_from_execution_receipt_v1(
            self.plan,
            self.launch,
            self.manifest,
            self.run_start,
            self.artifact_receipt,
            self.execution_receipt,
        )
        identity.assert_sealed()
        self.assertEqual(identity.adapter_digest, self.execution_receipt.adapter_digest)
        self.assertEqual(identity.training_run_digest, self.execution_receipt.digest)
        self.assertFalse(identity.authority)

    def test_tampered_execution_receipt_fails_closed(self):
        forged = replace(self.execution_receipt, completed_steps=124)
        with self.assertRaisesRegex(
            NativeTrainingExecutionError,
            "completed-step mismatch|execution receipt seal mismatch",
        ):
            forged.assert_for(
                self.plan,
                self.launch,
                self.manifest,
                self.run_start,
                self.artifact_receipt,
            )


if __name__ == "__main__":
    unittest.main()
