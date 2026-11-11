from dataclasses import replace
import json
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_balance_v1 import (
    BALANCED_FAMILY_COUNT,
    build_balanced_native_training_corpus_v1,
    require_native_training_balance_v1,
)
from koschei.native_intelligence_training_corpus_v1 import (
    DEFAULT_VARIANTS_PER_FAMILY,
    NativeTrainingCorpusError,
    SPLITS,
    STAGES,
    build_native_training_corpus_v1,
)
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingBalanceV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        cls.holdout = build_native_intelligence_holdout_v1(curriculum)
        cls.release = build_balanced_native_training_corpus_v1(
            cls.holdout,
            variants_per_family=1,
        )

    def test_default_balanced_release_is_two_thousand_six_hundred_eighty_eight(self):
        self.assertEqual(BALANCED_FAMILY_COUNT, 28)
        self.assertEqual(DEFAULT_VARIANTS_PER_FAMILY, 96)
        self.assertEqual(BALANCED_FAMILY_COUNT * DEFAULT_VARIANTS_PER_FAMILY, 2688)

    def test_small_balanced_release_is_deterministic_and_sealed(self):
        second = build_balanced_native_training_corpus_v1(
            self.holdout,
            variants_per_family=1,
        )
        self.assertEqual(self.release, second)
        self.release.assert_sealed(self.holdout)
        require_native_training_balance_v1(self.release)
        self.assertEqual(self.release.example_count, 28)
        self.assertEqual(len(self.release.family_splits), 28)
        self.assertFalse(self.release.authority)

    def test_every_stage_train_contains_accepted_and_rejected_supervision(self):
        for stage in STAGES:
            decisions = {
                json.loads(row.target_text)["decision"]
                for row in self.release.examples
                if row.stage == stage and row.split == "train"
            }
            self.assertEqual(decisions, {"ACCEPTED", "REJECTED"})

    def test_balanced_geometry_preserves_stage_and_split_isolation(self):
        self.assertEqual(dict(self.release.stage_counts), {stage: 4 for stage in STAGES})
        self.assertEqual(
            dict(self.release.split_counts),
            {"train": 14, "validation": 7, "test": 7},
        )
        observed = {}
        for example in self.release.examples:
            observed.setdefault(example.family, set()).add(example.split)
        self.assertEqual(len(observed), BALANCED_FAMILY_COUNT)
        self.assertTrue(all(len(splits) == 1 for splits in observed.values()))
        self.assertEqual(set(dict(self.release.split_counts)), set(SPLITS))

    def test_base_positive_only_train_release_is_not_training_ready(self):
        base = build_native_training_corpus_v1(self.holdout, variants_per_family=1)
        with self.assertRaisesRegex(
            NativeTrainingCorpusError,
            "must contain ACCEPTED and REJECTED train supervision",
        ):
            require_native_training_balance_v1(base)

    def test_relabeling_rejected_train_targets_breaks_balance(self):
        rows = []
        for example in self.release.examples:
            if example.stage == "N0" and example.split == "train":
                target = json.loads(example.target_text)
                if target["decision"] == "REJECTED":
                    target["decision"] = "ACCEPTED"
                    example = replace(
                        example,
                        target_text=json.dumps(
                            target,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
            rows.append(example)
        forged = replace(self.release, examples=tuple(rows))
        with self.assertRaisesRegex(
            NativeTrainingCorpusError,
            "N0 must contain ACCEPTED and REJECTED train supervision",
        ):
            require_native_training_balance_v1(forged)


if __name__ == "__main__":
    unittest.main()
