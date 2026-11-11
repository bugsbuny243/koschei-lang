import json
from pathlib import Path
import tempfile
import unittest

from koschei.native_model_curriculum_v2 import (
    NativeModelCurriculumError,
    build_native_model_curriculum_v2,
    load_native_model_curriculum_v2,
    verify_native_model_curriculum_v2,
    write_native_model_curriculum_v2,
)


def curriculum():
    return build_native_model_curriculum_v2(
        source_commit="a" * 40,
        parent_curriculum_digest="b" * 64,
    )


class NativeModelCurriculumV2Tests(unittest.TestCase):
    def test_n0_through_n6_are_oracle_backed_and_deterministic(self):
        first = curriculum()
        second = curriculum()

        self.assertEqual(first, second)
        self.assertEqual(first.case_count, 24)
        self.assertEqual(first.stage_counts["N0"], 3)
        self.assertEqual(first.stage_counts["N1"], 4)
        self.assertEqual(first.stage_counts["N2"], 4)
        self.assertEqual(first.stage_counts["N3"], 4)
        self.assertEqual(first.stage_counts["N4"], 2)
        self.assertEqual(first.stage_counts["N5"], 4)
        self.assertEqual(first.stage_counts["N6"], 3)
        self.assertEqual(first.accepted_count, 10)
        self.assertEqual(first.rejected_count, 14)
        self.assertEqual(len(first.curriculum_sha256), 64)

    def test_native_sigils_are_compiler_oracle_output(self):
        item = next(case for case in curriculum().cases if case.case_id == "n0-five-native-sigils")
        target = json.loads(item.target_text)

        self.assertEqual(target["decision"], "ACCEPTED")
        self.assertEqual(target["sigils"], ["ka", "vor", "shi", "thal", "nur"])
        self.assertEqual(len(target["native_mir_fingerprint"]), 64)
        self.assertEqual(len(target["typed_semantic_digest"]), 64)

    def test_same_language_profile_births_distinct_customer_veyras(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n1-same-language-distinct-customer-veyras"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertTrue(target["same_profile"])
        self.assertTrue(target["same_constitution"])
        self.assertTrue(target["distinct_customer_veyras"])
        self.assertNotEqual(target["veyra_a_digest"], target["veyra_b_digest"])

    def test_visible_copy_cannot_transfer_aevra_between_veyras(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n1-visible-copy-does-not-transfer-aevra"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertIn("different Veyra", target["reason"])

    def test_five_of_six_is_encoded_as_zero_not_partial_authority(self):
        item = next(case for case in curriculum().cases if case.case_id == "n2-five-of-six-is-zero")
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertEqual(target["partial_authority"], 0)
        self.assertIn("partial concurrence is zero", target["reason"])

    def test_cross_veyra_six_fragments_are_rejected(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n2-cross-veyra-fragments-are-zero"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertIn("same Veyra binding", target["reason"])

    def test_vormir_kills_old_epoch_before_successor_head(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n3-vormir-durable-epoch-sacrifice"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertEqual(target["sacrificed_epoch"], 7)
        self.assertEqual(target["successor_epoch"], 8)
        self.assertTrue(target["old_epoch_tombstoned"])
        self.assertTrue(target["successor_is_durable_head"])
        self.assertTrue(target["successor_born_inactive"])
        self.assertEqual(target["witness_domain_count"], 2)

    def test_morth_forbids_dead_aevra_future(self):
        item = next(
            case for case in curriculum().cases if case.case_id == "n3-morth-has-no-living-future"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "MORTH")
        self.assertFalse(target["resurrection_allowed"])
        self.assertIn("no living future", target["reason"])

    def test_nur_rotates_nyr_without_creating_authority(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n4-nur-rotates-nyr-without-authority"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertTrue(target["aliases_rotate"])
        self.assertTrue(target["canonical_sigils_stable"])
        self.assertFalse(target["stable_topology_labels"])
        self.assertFalse(target["authority"])
        self.assertNotEqual(target["surface_digest_a"], target["surface_digest_b"])

    def test_learning_pressure_can_contain_visibility_to_zero(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n4-contained-learning-pressure-exposes-no-nyr"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["learning_posture"], "contained")
        self.assertFalse(target["visibility_allowed"])
        self.assertEqual(target["root_budget"], 0)
        self.assertEqual(target["relation_budget"], 0)
        self.assertFalse(target["authority"])

    def test_survival_rejects_khar_violating_branch(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n5-survival-selects-least-loss-khar-future"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertTrue(target["unsafe_branch_rejected"])
        self.assertEqual(target["chosen_branch_digest"], "a" * 64)
        self.assertFalse(target["authority"])

    def test_bounded_autonomy_is_proposal_only(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n5-autonomy-proposes-but-cannot-authorize"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertFalse(target["authority"])
        self.assertEqual(target["proposal_round"], 3)
        self.assertEqual(target["chosen_branch_digest"], "a" * 64)

    def test_n6_requires_revalidated_adversarial_evidence(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n6-security-evidence-passes-native-adversarial-gate"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertTrue(target["security_specialization_admitted"])
        self.assertTrue(target["all_required_gates_passed"])
        self.assertTrue(target["minimum_matches_native_baseline"])
        self.assertGreaterEqual(target["total_tests_run"], target["minimum_total_tests"])

    def test_n6_missing_suite_fails_closed(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n6-missing-security-suite-fails-closed"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertFalse(target["security_specialization_admitted"])
        self.assertEqual(target["failed_gate"], "distribution-shift-observer")
        self.assertEqual(target["tests_run"], 0)
        self.assertIn("required suite missing", target["detail"])

    def test_n6_test_count_shrink_fails_closed(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n6-security-suite-shrink-is-rejected"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertFalse(target["security_specialization_admitted"])
        self.assertEqual(target["failed_gate"], "distribution-shift-observer")
        self.assertLess(target["tests_run"], target["minimum_tests"])
        self.assertIn("test-count shrink detected", target["detail"])

    def test_summary_or_case_tampering_breaks_release_digest(self):
        value = curriculum().to_dict()
        value["accepted_count"] = 99
        with self.assertRaisesRegex(NativeModelCurriculumError, "outcome counts mismatch"):
            verify_native_model_curriculum_v2(value)

        value = curriculum().to_dict()
        value["cases"][0]["task"] = "attacker relabelled task"
        with self.assertRaisesRegex(NativeModelCurriculumError, "digest mismatch"):
            verify_native_model_curriculum_v2(value)

    def test_write_load_round_trip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native-curriculum-v2.json"
            expected = curriculum()

            write_native_model_curriculum_v2(expected, path)
            self.assertEqual(load_native_model_curriculum_v2(path), expected)

            with self.assertRaises(FileExistsError):
                write_native_model_curriculum_v2(expected, path)


if __name__ == "__main__":
    unittest.main()
