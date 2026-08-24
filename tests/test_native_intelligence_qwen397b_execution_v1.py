from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_base_spec_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_qwen397b_execution_v1 import (
    Qwen397BExecutionError,
    build_qwen397b_native_intelligence_from_execution_receipt_v1,
    seal_qwen397b_training_execution_receipt_v1,
    seal_qwen397b_training_run_start_v1,
)
from koschei.native_intelligence_qwen397b_launch_v1 import seal_qwen397b_training_launch_v1
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
from koschei.native_intelligence_qwen397b_token_profile_v1 import (
    FORMATTING_VERSION_V1,
    seal_qwen397b_token_profile_v1,
)
from koschei.native_intelligence_qwen397b_training_plan_v1 import (
    seal_canonical_qwen397b_training_plan_v1,
)
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_execution_v1 import (
    NativeTrainingExecutionError,
    build_native_intelligence_from_execution_receipt_v1,
)
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_lineage_v1 import seal_native_training_receipt_v1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class Qwen397BExecutionV1Tests(unittest.TestCase):
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
        self.profile = canonical_qwen397b_koschei_profile_v1()
        self.preflight = seal_qwen397b_preflight_v1(
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
        counts = {row.split: row.example_count for row in self.manifest.files}
        self.token_profile = seal_qwen397b_token_profile_v1(
            self.manifest,
            self.profile,
            tokenizer_revision=CANONICAL_QWEN397B_REVISION_V1,
            formatting_version=FORMATTING_VERSION_V1,
            train_examples=counts["train"],
            validation_examples=counts["validation"],
            train_tokens=counts["train"] * 200,
            validation_tokens=counts["validation"] * 200,
            max_train_tokens=600,
            max_validation_tokens=600,
            train_truncated_examples=0,
            validation_truncated_examples=0,
        )
        self.plan = seal_canonical_qwen397b_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            preflight=self.preflight,
            token_profile=self.token_profile,
            profile=self.profile,
        )
        self.launch = seal_qwen397b_training_launch_v1(
            self.plan,
            self.manifest,
            self.preflight,
            self.token_profile,
            self.release,
            trainer_environment_digest="1" * 64,
            launcher_digest="2" * 64,
            profile=self.profile,
        )
        self.run_start = seal_qwen397b_training_run_start_v1(
            self.plan,
            self.launch,
            self.manifest,
            self.preflight,
            self.token_profile,
            provider="hf-jobs",
            job_reference_digest="3" * 64,
            start_evidence_digest="4" * 64,
            profile=self.profile,
        )
        self.artifact_receipt = seal_native_training_receipt_v1(
            self.plan,
            adapter_digest="5" * 64,
            final_checkpoint_digest="6" * 64,
            trainer_log_digest="7" * 64,
            completed_steps=123,
            completion_evidence_digest="8" * 64,
        )
        self.execution_receipt = seal_qwen397b_training_execution_receipt_v1(
            self.plan,
            self.launch,
            self.manifest,
            self.preflight,
            self.token_profile,
            self.run_start,
            self.artifact_receipt,
            profile=self.profile,
        )

    def test_qwen_specific_execution_bridge_mints_authority_free_identity(self):
        identity = build_qwen397b_native_intelligence_from_execution_receipt_v1(
            self.plan,
            self.launch,
            self.manifest,
            self.preflight,
            self.token_profile,
            self.run_start,
            self.artifact_receipt,
            self.execution_receipt,
            profile=self.profile,
        )
        identity.assert_sealed()
        self.assertEqual(identity.base_model_revision, CANONICAL_QWEN397B_REVISION_V1)
        self.assertEqual(identity.base_weights_digest, self.preflight.weights_identity_digest)
        self.assertEqual(identity.adapter_digest, self.execution_receipt.adapter_digest)
        self.assertEqual(identity.training_run_digest, self.execution_receipt.digest)
        self.assertFalse(identity.authority)

    def test_same_qwen_receipt_cannot_use_generic_identity_bridge(self):
        with self.assertRaisesRegex(
            NativeTrainingExecutionError,
            "model-family-specific execution bridge",
        ):
            build_native_intelligence_from_execution_receipt_v1(
                self.plan,
                self.launch,
                self.manifest,
                self.run_start,
                self.artifact_receipt,
                self.execution_receipt,
            )

    def test_qwen_execution_rejects_tampered_token_profile(self):
        forged = replace(self.token_profile, train_tokens=self.token_profile.train_tokens + 1)
        with self.assertRaises(Qwen397BExecutionError):
            build_qwen397b_native_intelligence_from_execution_receipt_v1(
                self.plan,
                self.launch,
                self.manifest,
                self.preflight,
                forged,
                self.run_start,
                self.artifact_receipt,
                self.execution_receipt,
                profile=self.profile,
            )


if __name__ == "__main__":
    unittest.main()
