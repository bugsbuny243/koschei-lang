from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_intelligence_training_launch_v1 import (
    NativeTrainingLaunchError,
    materialize_native_trainer_inputs_v1,
    seal_native_training_launch_v1,
)
from koschei.native_intelligence_training_lineage_v1 import seal_native_training_plan_v1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingLaunchV1Tests(unittest.TestCase):
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

    def launch(self):
        return seal_native_training_launch_v1(
            self.plan,
            self.manifest,
            self.release,
            trainer_environment_digest="4" * 64,
            launcher_digest="5" * 64,
        )

    def test_launch_exposes_only_train_and_validation_to_trainer(self):
        launch = self.launch()
        inputs = materialize_native_trainer_inputs_v1(
            launch,
            self.plan,
            self.manifest,
            self.release,
        )

        self.assertEqual(launch.gradient_source_split, "train")
        self.assertEqual(launch.validation_only_split, "validation")
        self.assertEqual(launch.sealed_test_split, "test")
        self.assertFalse(launch.test_exposed_to_trainer)
        self.assertFalse(launch.authority)
        self.assertEqual(inputs.gradient_source_splits, ("train",))
        self.assertEqual(inputs.evaluation_only_splits, ("validation",))
        self.assertIsNone(inputs.test_path)
        self.assertFalse(inputs.authority)
        self.assertTrue(Path(inputs.train_path).is_file())
        self.assertTrue(Path(inputs.validation_path).is_file())

    def test_modified_training_bytes_block_launch(self):
        with (self.release / "train.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")

        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "byte count mismatch|file digest mismatch|example count mismatch",
        ):
            self.launch()

    def test_modified_sealed_test_bytes_also_block_launch(self):
        with (self.release / "test.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")

        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "byte count mismatch|file digest mismatch|example count mismatch",
        ):
            self.launch()

    def test_bytes_changed_after_launch_block_trainer_materialization(self):
        launch = self.launch()
        with (self.release / "validation.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")

        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "byte count mismatch|file digest mismatch|example count mismatch",
        ):
            materialize_native_trainer_inputs_v1(
                launch,
                self.plan,
                self.manifest,
                self.release,
            )

    def test_forged_test_exposure_and_gradient_roles_fail_closed(self):
        launch = self.launch()
        exposed = replace(launch, test_exposed_to_trainer=True)
        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "test split cannot be exposed",
        ):
            exposed.assert_for(self.plan, self.manifest)

        wrong_gradient = replace(launch, gradient_source_split="validation")
        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "only train may be a gradient source",
        ):
            wrong_gradient.assert_for(self.plan, self.manifest)

    def test_fabricated_trainer_test_path_is_rejected(self):
        launch = self.launch()
        inputs = materialize_native_trainer_inputs_v1(
            launch,
            self.plan,
            self.manifest,
            self.release,
        )
        forged = replace(inputs, test_path=str(self.release / "test.jsonl"))
        with self.assertRaisesRegex(
            NativeTrainingLaunchError,
            "must not expose test path",
        ):
            forged.assert_for(launch)

    def test_launch_cannot_be_rebound_to_different_plan_or_export(self):
        launch = self.launch()
        foreign_plan = replace(self.plan, digest="f" * 64)
        with self.assertRaises(NativeTrainingLaunchError):
            launch.assert_for(foreign_plan, self.manifest)

        foreign_manifest = replace(self.manifest, digest="e" * 64)
        with self.assertRaises(NativeTrainingLaunchError):
            launch.assert_for(self.plan, foreign_manifest)


if __name__ == "__main__":
    unittest.main()
