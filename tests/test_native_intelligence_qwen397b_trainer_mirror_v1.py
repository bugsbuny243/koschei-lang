from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_trainer_mirror_v1 import (
    Qwen397BTrainerMirrorError,
    seal_qwen397b_trainer_mirror_v1,
)
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class Qwen397BTrainerMirrorV1Tests(unittest.TestCase):
    def setUp(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        holdout = build_native_intelligence_holdout_v1(curriculum)
        corpus = build_balanced_native_training_corpus_v1(holdout, variants_per_family=1)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = write_native_training_export_v1(
            holdout,
            corpus,
            Path(self.temp.name) / "release",
        )
        self.receipt = seal_qwen397b_trainer_mirror_v1(
            self.manifest,
            dataset_repo_id="koschei/test-qwen397b-trainer-mirror",
            resolved_revision="1" * 40,
            roundtrip_evidence_digest="2" * 64,
        )

    def test_receipt_exposes_only_train_validation_and_seals_test_sha(self):
        self.receipt.assert_for(self.manifest)
        rows = {row.split: row for row in self.manifest.files}
        self.assertEqual(self.receipt.train_sha256, rows["train"].sha256)
        self.assertEqual(self.receipt.validation_sha256, rows["validation"].sha256)
        self.assertEqual(self.receipt.sealed_test_sha256, rows["test"].sha256)
        self.assertFalse(self.receipt.test_exposed_to_trainer)
        self.assertFalse(hasattr(self.receipt, "test_filename"))
        self.assertFalse(self.receipt.authority)

    def test_foreign_export_cannot_reuse_mirror_receipt(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="c" * 40,
            parent_curriculum_digest="d" * 64,
        )
        holdout = build_native_intelligence_holdout_v1(curriculum)
        corpus = build_balanced_native_training_corpus_v1(holdout, variants_per_family=1)
        with tempfile.TemporaryDirectory() as directory:
            foreign = write_native_training_export_v1(
                holdout,
                corpus,
                Path(directory) / "release",
            )
            with self.assertRaisesRegex(
                Qwen397BTrainerMirrorError,
                "different training export",
            ):
                self.receipt.assert_for(foreign)

    def test_tamper_or_test_exposure_fails_closed(self):
        with self.assertRaisesRegex(Qwen397BTrainerMirrorError, "must not expose"):
            replace(self.receipt, test_exposed_to_trainer=True).assert_for(self.manifest)
        with self.assertRaisesRegex(Qwen397BTrainerMirrorError, "train_sha256 mismatch"):
            replace(self.receipt, train_sha256="f" * 64).assert_for(self.manifest)


if __name__ == "__main__":
    unittest.main()
