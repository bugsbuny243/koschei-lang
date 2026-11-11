from dataclasses import replace
import unittest

from koschei.native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from koschei.native_intelligence_training_corpus_v1 import (
    DEFAULT_VARIANTS_PER_FAMILY,
    GENERATOR_VERSION,
    NativeTrainingCorpusError,
    SPLITS,
    STAGES,
    build_native_training_corpus_v1,
)
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


class NativeIntelligenceTrainingCorpusV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curriculum = build_native_model_curriculum_v2(
            source_commit="a" * 40,
            parent_curriculum_digest="b" * 64,
        )
        cls.holdout = build_native_intelligence_holdout_v1(curriculum)
        cls.release = build_native_training_corpus_v1(cls.holdout, variants_per_family=2)

    def test_default_release_is_two_thousand_sixteen_oracle_variants(self):
        self.assertEqual(DEFAULT_VARIANTS_PER_FAMILY, 96)
        self.assertEqual(len(self.release.family_splits), 21)
        self.assertEqual(21 * DEFAULT_VARIANTS_PER_FAMILY, 2016)

    def test_small_release_is_deterministic_and_sealed(self):
        first = self.release
        second = build_native_training_corpus_v1(self.holdout, variants_per_family=2)
        self.assertEqual(first, second)
        first.assert_sealed(self.holdout)
        self.assertEqual(first.generator_version, GENERATOR_VERSION)
        self.assertFalse(first.authority)
        self.assertEqual(first.example_count, 42)
        self.assertEqual(len(first.digest), 64)

    def test_every_stage_has_an_independent_family_in_every_split(self):
        release = self.release
        self.assertEqual(dict(release.stage_counts), {stage: 6 for stage in STAGES})
        self.assertEqual(dict(release.split_counts), {split: 14 for split in SPLITS})
        observed = {(row.stage, row.split) for row in release.examples}
        self.assertEqual(observed, {(stage, split) for stage in STAGES for split in SPLITS})

    def test_one_oracle_family_never_crosses_split_boundary(self):
        observed = {}
        for example in self.release.examples:
            observed.setdefault(example.family, set()).add(example.split)
        self.assertTrue(all(len(splits) == 1 for splits in observed.values()))
        self.assertEqual(
            tuple(sorted((family, next(iter(splits))) for family, splits in observed.items())),
            self.release.family_splits,
        )

    def test_training_examples_do_not_reuse_constitutional_holdout_inputs(self):
        holdout_ids = {row.case_id for row in self.holdout.cases}
        holdout_inputs = {row.input_digest for row in self.holdout.cases}
        holdout_pairs = {row.pair_digest for row in self.holdout.cases}
        for example in self.release.examples:
            self.assertNotIn(example.example_id, holdout_ids)
            self.assertNotIn(example.input_digest, holdout_inputs)
            self.assertNotIn(example.pair_digest, holdout_pairs)

    def test_split_digests_are_distinct_and_bound_to_release(self):
        digests = dict(self.release.split_digests)
        self.assertEqual(set(digests), set(SPLITS))
        self.assertEqual(len(set(digests.values())), 3)
        for split in SPLITS:
            self.assertEqual(self.release.split_digest(split), digests[split])

    def test_tampered_example_breaks_release_seal(self):
        examples = list(self.release.examples)
        examples[0] = replace(examples[0], task=examples[0].task + " forged")
        forged = replace(self.release, examples=tuple(examples))
        with self.assertRaisesRegex(NativeTrainingCorpusError, "example seal mismatch"):
            forged.assert_sealed(self.holdout)

    def test_family_split_tamper_fails_closed(self):
        family_splits = list(self.release.family_splits)
        family, split = family_splits[0]
        family_splits[0] = (family, "test" if split != "test" else "train")
        forged = replace(self.release, family_splits=tuple(family_splits))
        with self.assertRaisesRegex(NativeTrainingCorpusError, "family_splits mismatch"):
            forged.assert_sealed(self.holdout)


if __name__ == "__main__":
    unittest.main()
