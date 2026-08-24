from dataclasses import replace
import unittest

from koschei.native_intelligence_holdout_v1 import (
    build_native_intelligence_holdout_v1,
)
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

    def plan(self):
        return seal_native_training_plan_v1(
            self.holdout,
            base_model_revision="1" * 40,
            base_weights_digest="2" * 64,
            training_corpus_digest="3" * 64,
            train_split_digest="4" * 64,
            validation_split_digest="5" * 64,
            test_split_digest="6" * 64,
            training_config_digest="7" * 64,
            training_method="lora-sft-v1",
        )

    def test_plan_binds_base_source_holdout_splits_and_config_before_training(self):
        plan = self.plan()
        plan.assert_sealed()

        self.assertEqual(plan.base_model_id, CANONICAL_BASE_MODEL_V1)
        self.assertEqual(plan.source_commit, "a" * 40)
        self.assertEqual(plan.curriculum_digest, self.holdout.curriculum_digest)
        self.assertEqual(plan.constitutional_holdout_digest, self.holdout.digest)
        self.assertFalse(plan.authority)
        self.assertEqual(len(plan.digest), 64)

    def test_training_plan_is_deterministic(self):
        self.assertEqual(self.plan(), self.plan())

    def test_split_identity_cannot_collapse_or_reuse_holdout(self):
        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "split digests must be distinct",
        ):
            seal_native_training_plan_v1(
                self.holdout,
                base_model_revision="1" * 40,
                base_weights_digest="2" * 64,
                training_corpus_digest="3" * 64,
                train_split_digest="4" * 64,
                validation_split_digest="4" * 64,
                test_split_digest="6" * 64,
                training_config_digest="7" * 64,
                training_method="lora-sft-v1",
            )

        with self.assertRaisesRegex(
            NativeIntelligenceTrainingLineageError,
            "holdout cannot be reused",
        ):
            seal_native_training_plan_v1(
                self.holdout,
                base_model_revision="1" * 40,
                base_weights_digest="2" * 64,
                training_corpus_digest=self.holdout.digest,
                train_split_digest="4" * 64,
                validation_split_digest="5" * 64,
                test_split_digest="6" * 64,
                training_config_digest="7" * 64,
                training_method="lora-sft-v1",
            )

    def test_completed_training_is_receipt_not_deployment_authority(self):
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

    def test_receipt_builds_exact_existing_native_intelligence_identity(self):
        plan = self.plan()
        receipt = seal_native_training_receipt_v1(
            plan,
            adapter_digest="8" * 64,
            final_checkpoint_digest="9" * 64,
            trainer_log_digest="a" * 64,
            completed_steps=123,
            completion_evidence_digest="b" * 64,
        )
        identity = build_native_intelligence_from_training_receipt_v1(plan, receipt)

        identity.assert_sealed()
        self.assertEqual(identity.base_model_revision, plan.base_model_revision)
        self.assertEqual(identity.base_weights_digest, plan.base_weights_digest)
        self.assertEqual(identity.curriculum_digest, self.holdout.curriculum_digest)
        self.assertEqual(identity.adapter_digest, receipt.adapter_digest)
        self.assertEqual(identity.training_run_digest, receipt.digest)
        self.assertEqual(identity.training_method, plan.training_method)
        self.assertFalse(identity.authority)

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
