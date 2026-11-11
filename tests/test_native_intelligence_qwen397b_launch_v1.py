from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.local_validation_v1 import (
    seal_local_validation_receipt_v1,
    seal_local_validation_step_v1,
)
from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_base_spec_v1 import (
    CANONICAL_QWEN397B_REVISION_V1,
    CANONICAL_QWEN397B_TRAINING_METHOD_V1,
)
from koschei.native_intelligence_qwen397b_launch_v1 import (
    Qwen397BLaunchError,
    materialize_qwen397b_trainer_inputs_v1,
    seal_qwen397b_training_launch_v1,
)
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
from koschei.native_intelligence_qwen397b_training_plan_v1 import seal_canonical_qwen397b_training_plan_v1
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_lineage_v1 import seal_native_training_plan_v1
from koschei.native_intelligence_v1 import CANONICAL_BASE_MODEL_V1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


def validation_receipt(*, source_commit: str = "a" * 40, profile: str = "full", clean: bool = True):
    step = seal_local_validation_step_v1(
        step_id="full-validation",
        command=("ks-local-validate", "--profile", "full"),
        returncode=0,
        stdout_sha256="d" * 64,
        stderr_sha256="e" * 64,
    )
    return seal_local_validation_receipt_v1(
        source_commit=source_commit,
        checkout_clean=clean,
        profile=profile,
        python_version="Python 3.12.0",
        go_version="go version go1.21 linux/amd64",
        platform="Linux-test",
        steps=(step,),
    )


class Qwen397BLaunchV1Tests(unittest.TestCase):
    def setUp(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        self.holdout = build_native_intelligence_holdout_v1(curriculum)
        self.corpus = build_balanced_native_training_corpus_v1(
            self.holdout, variants_per_family=1
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.release = Path(self.temp.name) / "release"
        self.manifest = write_native_training_export_v1(
            self.holdout, self.corpus, self.release
        )
        self.profile = canonical_qwen397b_koschei_profile_v1()
        self.validation = validation_receipt()
        self.preflight = seal_qwen397b_preflight_v1(
            repo_id=CANONICAL_BASE_MODEL_V1,
            requested_revision=CANONICAL_QWEN397B_REVISION_V1,
            resolved_revision=CANONICAL_QWEN397B_REVISION_V1,
            shard_count=94,
            weight_bytes=807_000_000_000,
            safetensors_index_sha256="a" * 64,
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
            train_tokens=counts["train"] * 120,
            validation_tokens=counts["validation"] * 120,
            max_train_tokens=450,
            max_validation_tokens=450,
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

    def launch(self, validation=None):
        return seal_qwen397b_training_launch_v1(
            self.plan,
            self.manifest,
            self.preflight,
            self.token_profile,
            validation or self.validation,
            self.release,
            trainer_environment_digest="b" * 64,
            launcher_digest="c" * 64,
            profile=self.profile,
        )

    def test_qwen_launch_rechecks_full_plan_validation_and_exposes_no_test_path(self):
        launch = self.launch()
        inputs = materialize_qwen397b_trainer_inputs_v1(
            launch,
            self.plan,
            self.manifest,
            self.preflight,
            self.token_profile,
            self.validation,
            self.release,
            profile=self.profile,
        )
        self.assertIsNone(inputs.test_path)
        self.assertEqual(inputs.gradient_source_splits, ("train",))
        self.assertEqual(inputs.evaluation_only_splits, ("validation",))
        self.assertFalse(launch.authority)

    def test_stale_core_or_dirty_validation_blocks_qwen_launch(self):
        invalid_receipts = (
            validation_receipt(source_commit="c" * 40),
            validation_receipt(profile="core"),
            validation_receipt(clean=False),
        )
        for receipt in invalid_receipts:
            with self.assertRaises(Qwen397BLaunchError):
                self.launch(receipt)

    def test_tampered_token_preflight_blocks_qwen_launch(self):
        forged = replace(self.token_profile, train_truncated_examples=1)
        with self.assertRaises(Qwen397BLaunchError):
            seal_qwen397b_training_launch_v1(
                self.plan,
                self.manifest,
                self.preflight,
                forged,
                self.validation,
                self.release,
                trainer_environment_digest="b" * 64,
                launcher_digest="c" * 64,
                profile=self.profile,
            )

    def test_generic_static_profile_plan_cannot_use_qwen_launch_boundary(self):
        generic = seal_native_training_plan_v1(
            self.holdout,
            self.corpus,
            self.manifest,
            base_model_revision=CANONICAL_QWEN397B_REVISION_V1,
            base_weights_digest=self.preflight.weights_identity_digest,
            training_config_digest=self.profile.digest,
            training_method=CANONICAL_QWEN397B_TRAINING_METHOD_V1,
        )
        with self.assertRaisesRegex(Qwen397BLaunchError, "run-config digest mismatch"):
            seal_qwen397b_training_launch_v1(
                generic,
                self.manifest,
                self.preflight,
                self.token_profile,
                self.validation,
                self.release,
                trainer_environment_digest="b" * 64,
                launcher_digest="c" * 64,
                profile=self.profile,
            )

    def test_export_byte_tamper_blocks_qwen_launch(self):
        with (self.release / "train.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")
        with self.assertRaises(Qwen397BLaunchError):
            self.launch()


if __name__ == "__main__":
    unittest.main()
