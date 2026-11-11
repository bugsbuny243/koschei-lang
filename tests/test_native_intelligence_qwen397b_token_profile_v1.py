from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_qwen397b_base_spec_v1 import CANONICAL_QWEN397B_REVISION_V1
from koschei.native_intelligence_qwen397b_profile_v1 import canonical_qwen397b_koschei_profile_v1
from koschei.native_intelligence_qwen397b_token_profile_v1 import (
    FORMATTING_VERSION_V1,
    Qwen397BTokenProfileError,
    seal_qwen397b_token_profile_v1,
)
from koschei.native_intelligence_training_balance_v1 import build_balanced_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class Qwen397BTokenProfileV1Tests(unittest.TestCase):
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
        self.manifest = write_native_training_export_v1(
            self.holdout,
            self.corpus,
            Path(self.temp.name) / "release",
        )
        self.profile = canonical_qwen397b_koschei_profile_v1()
        counts = {row.split: row.example_count for row in self.manifest.files}
        self.train_count = counts["train"]
        self.validation_count = counts["validation"]

    def seal(self, **overrides):
        values = {
            "tokenizer_revision": CANONICAL_QWEN397B_REVISION_V1,
            "formatting_version": FORMATTING_VERSION_V1,
            "train_examples": self.train_count,
            "validation_examples": self.validation_count,
            "train_tokens": self.train_count * 200,
            "validation_tokens": self.validation_count * 200,
            "max_train_tokens": 600,
            "max_validation_tokens": 600,
            "train_truncated_examples": 0,
            "validation_truncated_examples": 0,
        }
        values.update(overrides)
        return seal_qwen397b_token_profile_v1(
            self.manifest,
            self.profile,
            **values,
        )

    def test_zero_truncation_profile_seals_exact_train_validation_export(self):
        evidence = self.seal()
        evidence.assert_for(self.manifest, self.profile)
        self.assertEqual(evidence.training_export_digest, self.manifest.digest)
        self.assertEqual(evidence.max_length, 4096)
        self.assertEqual(evidence.train_truncated_examples, 0)
        self.assertEqual(evidence.validation_truncated_examples, 0)
        self.assertFalse(evidence.authority)

    def test_any_train_or_validation_truncation_fails_closed(self):
        for field in ("train_truncated_examples", "validation_truncated_examples"):
            with self.assertRaisesRegex(
                Qwen397BTokenProfileError,
                "forbids silent train/validation truncation",
            ):
                self.seal(**{field: 1})

    def test_foreign_export_cannot_reuse_token_profile(self):
        evidence = self.seal()
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
                Qwen397BTokenProfileError,
                "different training export",
            ):
                evidence.assert_for(foreign_manifest, self.profile)

    def test_tokenizer_revision_or_formatting_drift_is_rejected(self):
        with self.assertRaisesRegex(Qwen397BTokenProfileError, "tokenizer revision drift"):
            self.seal(tokenizer_revision="1" * 40)
        with self.assertRaisesRegex(Qwen397BTokenProfileError, "formatting version drift"):
            self.seal(formatting_version="other-format")

    def test_test_split_is_not_part_of_trainer_token_profile(self):
        evidence = self.seal()
        self.assertFalse(hasattr(evidence, "test_examples"))
        self.assertFalse(hasattr(evidence, "test_tokens"))
        self.assertFalse(hasattr(evidence, "max_test_tokens"))

    def test_tampered_profile_digest_fails_closed(self):
        evidence = self.seal()
        forged = replace(evidence, train_tokens=evidence.train_tokens + 1)
        with self.assertRaisesRegex(Qwen397BTokenProfileError, "seal mismatch"):
            forged.assert_for(self.manifest, self.profile)


if __name__ == "__main__":
    unittest.main()
