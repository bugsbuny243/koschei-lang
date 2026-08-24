from pathlib import Path
import tempfile
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_corpus_cli_v1 import build_parser, main
from koschei.native_intelligence_training_corpus_v1 import DEFAULT_VARIANTS_PER_FAMILY, build_native_training_corpus_v1
from koschei.native_intelligence_training_export_v1 import write_native_training_export_v1
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingCorpusCliV1Tests(unittest.TestCase):
    def test_build_parser_defaults_to_full_two_thousand_sixteen_release(self):
        args = build_parser().parse_args([
            "build",
            "--curriculum", "curriculum.json",
            "--output-dir", "release",
        ])
        self.assertEqual(args.variants_per_family, DEFAULT_VARIANTS_PER_FAMILY)
        self.assertEqual(DEFAULT_VARIANTS_PER_FAMILY * 21, 2016)

    def test_verify_cli_checks_manifest_and_exact_split_bytes(self):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        holdout = build_native_intelligence_holdout_v1(curriculum)
        corpus = build_native_training_corpus_v1(holdout, variants_per_family=1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            write_native_training_export_v1(holdout, corpus, output)
            self.assertEqual(main(["verify", str(output)]), 0)


if __name__ == "__main__":
    unittest.main()
