from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_corpus_v1 import build_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_lineage_v1 import (
    NativeIntelligenceTrainingLineageError,
    build_native_intelligence_from_training_receipt_v1,
    seal_native_training_plan_v1,
    seal_native_training_receipt_v1,
)
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingLineageV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        cls.holdout = build_native_intelligence_holdout_v1(curriculum)
        cls.corpus = build_balanced_native_training_corpus_v1(
            cls.holdout,
            variants_per_family=1,
        )
        cls.export_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.export_temp.cleanup)
        cls.export_manifest = write_native_training_export_v1(
            cls.holdout,
            cls.corpus,
            Path(cls.export_temp.name) / "release",
        )

    def plan(self):
        return seal_native_training_plan_v1(
            self.holdout,
            self.corpus,
            self.export_manifest,
            base_model_revision="1" * 40,
            base_weights_digest="2" * 64,
            training_config_digest="7" * 64,
            training_method="lora-sft-v1",
        )

    def test_plan_binds_balanced_corpus_and_exact_export_before_compute(self):
        plan = self.plan()
        plan.assert_sealed()

        self.assertEqual(plan.base_model_id, CANONICAL_BASE_MODEL_V1)
        self.assertEqual(plan.source_commit, "a" * 40)
        self.assertEqual(plan.curriculum_digest, self.holdout.curriculum_digest)
        self.assertEqual(plan.constitutional_holdout_digest, self.holdout.digest)
        self.assertEqual(plan.training_corpus_digest, self.corpus.digest)
        self.assertEqual(plan.training_export_digest, self.export_manifest.digest)
        self.assertEqual(plan.train_split_digest, self.corpus.split_digest("train"))
        self.assertEqual(plan.validation_split_digest, self.corpus.split_digest("validation"))
        self.assertEqual(plan.test_split_digest, self.corpus.split_digest("test"))
        self.assertFalse(plan.authority)
        self.assertEqual(len(plan.digest), 64)

    def test_training_plan_is_deterministic(self):
        self.assertEqual(self.plan(), self.plan())

    def test_unbalanced_base_corpus_cannot_become_training_plan(self):
        base = build_native_training_corpus_v1(self.holdout, variants_per_family=1)
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_native_training_export_v1(
                self.holdout,
                base,
                Path(directory) / "release",
            )
            with self.assertRaisesRegex(
                NativeIntelligenceTrainingLineageError,
                "must contain ACCEPTED and REJECTED train supervision",
            ):
                seal_native_training_plan_v1(
                    self.holdout,
                    base,
                    manifest,
                    base_model_revision="1" * 40,
                    base_weights_digest="2" * 64,
                    training_config_digest="7" * 64,
                    training_method="lora-sft-v1",
                )

    def test_foreign_holdout_corpus_is_rejected_before_plan_seal(self):
        foreign_curriculum = build_native_model_curriculum_v2(
            source_commit="c" * 40,
            parent_curriculum_digest="d" * 64,
        )
        foreign_holdout = build_native_intelligence_holdout_v1(foreign_curriculum)
        foreign_corpus = build_balanced_native_training_corpus_v1(
            foreign_holdout,
            variants_per_family=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            foreign_manifest = write_native_training_export_v1(
                foreign_holdout,
                foreign_corpus,
                Path(directory) / "release",
            )
            with self.assertRaisesRegex(
                NativeIntelligenceTrainingLineageError,
                "different source commit|different constitutional holdout",
            ):
                seal_native_training_plan_v1(
                    self.holdout,
                    foreign_corpus,
                    foreign_manifest,
                    base_model_revision="1" * 40,
                    base_weights_digest="2" * 64,
                    training_config_digest="7" * 64,
                    training_method="lora-sft-v1",
                )

    def test_tampered_corpus_or_export_is_rejected_before_plan_seal(self):
        forged_corpus = replace(self.corpus, digest="f" * 64)
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "corpus release seal mismatch",
        ):
            seal_native_training_plan_v1(
                self.holdout,
                forged_corpus,
                self.export_manifest,
                base_model_revision="1" * 40,
                base_weights_digest="2" * 64,
                training_config_digest="7" * 64,
                training_method="lora-sft-v1",
            )

        forged_manifest = replace(self.export_manifest, digest="e" * 64)
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "export manifest seal mismatch",
        ):
            seal_native_training_plan_v1(
                self.holdout,
                self.corpus,
                forged_manifest,
                base_model_revision="1" * 40,
                base_weights_digest="2" * 64,
                training_config_digest="7" * 64,
                training_method="lora-sft-v1",
            )

    def test_completed_training_is_artifact_receipt_not_deployment_authority(self):
        plan = self.plan()
        receipt = seal_native_training_receipt_v1(
            plan,
            adapter_digest="8" * 64,
            final_checkpoint_digest="9" * 64,
            trainer_log_digest="a" * 64,
            completed_steps=123,
            completion_evidence_digest="b" * 64,
        )
        receipt.assert_for(plan)

        self.assertFalse(receipt.authority)
        self.assertFalse(receipt.deployment_approved)
        self.assertEqual(receipt.completed_steps, 123)
        self.assertEqual(len(receipt.digest), 64)

    def test_artifact_receipt_cannot_directly_create_model_identity(self):
        plan = self.plan()
        receipt = seal_native_training_receipt_v1(
            plan,
            adapter_digest="8" * 64,
            final_checkpoint_digest="9" * 64,
            trainer_log_digest="a" * 64,
            completed_steps=123,
            completion_evidence_digest="b" * 64,
        )
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "artifact receipt cannot create native intelligence",
        ):
            build_native_intelligence_from_training_receipt_v1(plan, receipt)

    def test_tampered_plan_or_receipt_fails_closed(self):
        plan = self.plan()
        forged_plan = replace(plan, training_config_digest="f" * 64)
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "plan seal mismatch",
        ):
            forged_plan.assert_sealed()

        receipt = seal_native_training_receipt_v1(
            plan,
            adapter_digest="8" * 64,
            final_checkpoint_digest="9" * 64,
            trainer_log_digest="a" * 64,
            completed_steps=123,
            completion_evidence_digest="b" * 64,
        )
        forged_receipt = replace(receipt, completed_steps=124)
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "receipt seal mismatch",
        ):
            forged_receipt.assert_for(plan)


if __name__ == "__main__":
    unittest.main()
