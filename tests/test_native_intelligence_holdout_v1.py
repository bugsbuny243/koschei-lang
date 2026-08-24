from dataclasses import replace
import unittest

from koschei.native_intelligence_holdout_v1 import (
    NativeIntelligenceHoldoutError,
    build_native_intelligence_holdout_v1,
    fingerprint_training_example_v1,
    require_training_disjoint_from_holdout_v1,
)
from koschei.native_model_curriculum_v2 import (
    STAGES,
    build_native_model_curriculum_v2,
)


def curriculum():
    return build_native_model_curriculum_v2(
        source_commit="a" * 40,
        parent_curriculum_digest="b" * 64,
    )


class NativeIntelligenceHoldoutV1Tests(unittest.TestCase):
    def test_complete_n0_n6_curriculum_is_sealed_as_evaluation_only(self):
        source = curriculum()
        holdout = build_native_intelligence_holdout_v1(source)

        holdout.assert_sealed()
        self.assertEqual(holdout.case_count, source.case_count)
        self.assertEqual(holdout.case_count, 24)
        self.assertFalse(holdout.training_inclusion_allowed)
        self.assertEqual(holdout.curriculum_digest, source.curriculum_sha256)
        self.assertEqual(
            holdout.stage_counts,
            tuple((stage, source.stage_counts[stage]) for stage in STAGES),
        )
        self.assertEqual(len({case.case_id for case in holdout.cases}), 24)

    def test_holdout_release_is_deterministic(self):
        source = curriculum()
        first = build_native_intelligence_holdout_v1(source)
        second = build_native_intelligence_holdout_v1(source)
        self.assertEqual(first, second)
        self.assertEqual(len(first.digest), 64)

    def test_exact_holdout_input_cannot_enter_training_under_new_id(self):
        source = curriculum()
        holdout = build_native_intelligence_holdout_v1(source)
        case = source.cases[0]
        leaked = fingerprint_training_example_v1(
            example_id="training-copy-001",
            input_text=case.input_text,
            target_text=case.target_text,
        )

        with self.assertRaisesRegex(
            NativeIntelligenceHoldoutError,
            "reuses constitutional holdout input",
        ):
            require_training_disjoint_from_holdout_v1(holdout, (leaked,))

    def test_holdout_case_identity_cannot_be_relabelled_into_training(self):
        source = curriculum()
        holdout = build_native_intelligence_holdout_v1(source)
        case = source.cases[0]
        relabelled = fingerprint_training_example_v1(
            example_id=case.case_id,
            input_text="synthetic variant input that is not the holdout input",
            target_text="synthetic variant target",
        )

        with self.assertRaisesRegex(
            NativeIntelligenceHoldoutError,
            "reuses constitutional holdout case identity",
        ):
            require_training_disjoint_from_holdout_v1(holdout, (relabelled,))

    def test_distinct_oracle_variant_may_be_considered_for_training(self):
        holdout = build_native_intelligence_holdout_v1(curriculum())
        candidate = fingerprint_training_example_v1(
            example_id="n0-training-variant-0001",
            input_text="ka treasury_variant; vor withdrawal_variant; shi evidence_variant;",
            target_text='{"decision":"ACCEPTED","source":"separate-oracle-variant"}',
        )

        accepted = require_training_disjoint_from_holdout_v1(holdout, (candidate,))
        self.assertEqual(accepted, (candidate,))

    def test_tampered_holdout_and_training_admission_fail_closed(self):
        holdout = build_native_intelligence_holdout_v1(curriculum())
        forged = replace(holdout, digest="f" * 64)
        with self.assertRaisesRegex(
            NativeIntelligenceHoldoutError,
            "release seal mismatch",
        ):
            forged.assert_sealed()

        trainable = replace(holdout, training_inclusion_allowed=True)
        with self.assertRaisesRegex(
            NativeIntelligenceHoldoutError,
            "cannot be admitted as training data",
        ):
            trainable.assert_sealed()


if __name__ == "__main__":
    unittest.main()
