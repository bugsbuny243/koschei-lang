import json
from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_corpus_v1 import build_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import (
    NativeTrainingExportError,
    verify_native_training_export_v1,
    write_native_training_export_v1,
)
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingExportV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        cls.holdout = build_native_intelligence_holdout_v1(curriculum)
        cls.corpus = build_native_training_corpus_v1(cls.holdout, variants_per_family=1)

    def test_export_writes_three_physically_separate_splits_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            manifest = write_native_training_export_v1(self.holdout, self.corpus, output)
            manifest.assert_sealed()
            verify_native_training_export_v1(manifest, output)

            self.assertEqual([row.split for row in manifest.files], ["train", "validation", "test"])
            self.assertEqual(sum(row.example_count for row in manifest.files), self.corpus.example_count)
            self.assertEqual(len({row.sha256 for row in manifest.files}), 3)
            self.assertTrue((output / "train.jsonl").is_file())
            self.assertTrue((output / "validation.jsonl").is_file())
            self.assertTrue((output / "test.jsonl").is_file())
            self.assertTrue((output / "manifest.json").is_file())

            rows = [json.loads(line) for line in (output / "test.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row["split"] == "test" for row in rows))
            self.assertTrue(all(row["authority"] is False for row in rows))

    def test_export_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            write_native_training_export_v1(self.holdout, self.corpus, output)
            with self.assertRaises(FileExistsError):
                write_native_training_export_v1(self.holdout, self.corpus, output)

    def test_modified_split_bytes_fail_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            manifest = write_native_training_export_v1(self.holdout, self.corpus, output)
            with (output / "train.jsonl").open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            with self.assertRaisesRegex(
                NativeTrainingExportError,
                "byte count mismatch|file digest mismatch|example count mismatch",
            ):
                verify_native_training_export_v1(manifest, output)


if __name__ == "__main__":
    unittest.main()
