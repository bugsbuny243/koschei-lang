from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_preflight_v1 import seal_qwen397b_preflight_v1
from koschei.native_intelligence_qwen397b_profile_v1 import (
    OFFICIAL_ARCHITECTURE,
    OFFICIAL_EXPERTS,
    OFFICIAL_EXPERTS_PER_TOKEN,
    OFFICIAL_MAX_POSITION_EMBEDDINGS,
    OFFICIAL_TEXT_HIDDEN_SIZE,
    OFFICIAL_TEXT_LAYERS,
    canonical_qwen397b_koschei_profile_v1,
)
from koschei.native_intelligence_qwen397b_training_plan_v1 import (
    CANONICAL_QWEN397B_REVISION_V1,
    CANONICAL_QWEN397B_TRAINING_METHOD_V1,
    Qwen397BTrainingPlanError,
    require_canonical_qwen397b_training_plan_v1,
    seal_canonical_qwen397b_training_plan_v1,
)
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_lineage_v1 import seal_native_training_plan_v1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


def base_preflight():
    return seal_qwen397b_preflight_v1(
        repo_id=CANONICAL_BASE_MODEL_V1,
        requested_revision=CANONICAL_QWEN397B_REVISION_V1,
        resolved_revision=CANONICAL_QWEN397B_REVISION_V1,
        shard_count=94,
        weight_bytes=807_000_000_000,
        safetensors_index_sha256="f" * 64,
        architecture=OFFICIAL_ARCHITECTURE,
        text_hidden_size=OFFICIAL_TEXT_HIDDEN_SIZE,
        text_layers=OFFICIAL_TEXT_LAYERS,
        experts=OFFICIAL_EXPERTS,
        experts_per_token=OFFICIAL_EXPERTS_PER_TOKEN,
        native_context=OFFICIAL_MAX_POSITION_EMBEDDINGS,
    )


class Qwen397BTrainingPlanV1Tests(unittest.TestCase):
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
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.manifest = write_native_training_export_v1(
            cls.holdout,
            cls.corpus,
            Path(cls.temp.name) / "release",
        )
        cls.profile = canonical_qwen397b_koschei_profile_v1()
        cls.preflight = base_preflight()

    def test_canonical_plan_pins_preflight_revision_profile_and_method(self):
        plan = seal_canonical_qwen397b_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            preflight=self.preflight,
            profile=self.profile,
        )
        require_canonical_qwen397b_training_plan_v1(plan, self.profile)
        self.assertEqual(plan.base_model_revision, CANONICAL_QWEN397B_REVISION_V1)
        self.assertEqual(plan.base_weights_digest, self.preflight.weights_identity_digest)
        self.assertEqual(plan.training_config_digest, self.profile.digest)
        self.assertEqual(plan.training_method, CANONICAL_QWEN397B_TRAINING_METHOD_V1)

    def test_missing_or_tampered_preflight_cannot_create_canonical_plan(self):
        with self.assertRaisesRegex(Qwen397BTrainingPlanError, "preflight evidence required"):
            seal_canonical_qwen397b_training_plan_v1(
                self.holdout,
                self.corpus,
                self.manifest,
                preflight=None,
                profile=self.profile,
            )

        forged = replace(self.preflight, shard_count=93)
        with self.assertRaises(Qwen397BTrainingPlanError):
            seal_canonical_qwen397b_training_plan_v1(
                self.holdout,
                self.corpus,
                self.manifest,
                preflight=forged,
                profile=self.profile,
            )

    def test_generic_plan_with_other_revision_is_not_canonical_397b_run(self):
        plan = seal_native_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            base_model_revision="2" * 40,
            base_weights_digest=self.preflight.weights_identity_digest,
            training_config_digest=self.profile.digest,
            training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        )
        with self.assertRaisesRegex(Qwen397BTrainingPlanError, "base revision drift"):
            require_canonical_qwen397b_training_plan_v1(plan, self.profile)

    def test_generic_plan_with_other_training_profile_is_not_canonical_397b_run(self):
        plan = seal_native_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            base_model_revision=CANONICAL_QWEN397B_REVISION_V1,
            base_weights_digest=self.preflight.weights_identity_digest,
            training_config_digest="3" * 64,
            training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        )
        with self.assertRaisesRegex(Qwen397BTrainingPlanError, "profile digest mismatch"):
            require_canonical_qwen397b_training_plan_v1(plan, self.profile)

    def test_tampered_canonical_profile_is_rejected_before_plan(self):
        forged = replace(self.profile, freeze_router=False)
        with self.assertRaises(ValueError):
            seal_canonical_qwen397b_training_plan_v1(
                self.holdout,
                self.corpus,
                self.manifest,
                preflight=self.preflight,
                profile=forged,
            )


if __name__ == "__main__":
    unittest.main()
