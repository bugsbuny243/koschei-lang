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
    def test_native_curriculum_through_n5_is_oracle_backed_and_deterministic(self):
        first = curriculum()
        second = curriculum()

        self.assertEqual(first, second)
        self.assertEqual(first.case_count, 17)
        self.assertEqual(first.stage_counts["N0"], 3)
        self.assertEqual(first.stage_counts["N1"], 0)
        self.assertEqual(first.stage_counts["N2"], 4)
        self.assertEqual(first.stage_counts["N3"], 4)
        self.assertEqual(first.stage_counts["N4"], 2)
        self.assertEqual(first.stage_counts["N5"], 4)
        self.assertEqual(first.stage_counts["N6"], 0)
        self.assertEqual(first.accepted_count, 7)
        self.assertEqual(first.rejected_count, 10)
        self.assertEqual(len(first.curriculum_sha256), 64)

    def test_five_of_six_is_encoded_as_zero_not_partial_authority(self):
        item = next(
            case for case in curriculum().cases if case.case_id == "n2-five-of-six-is-zero"
        )
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

    def test_native_sigils_are_compiler_oracle_output(self):
        item = next(
            case for case in curriculum().cases if case.case_id == "n0-five-native-sigils"
        )
        target = json.loads(item.target_text)

        self.assertEqual(target["decision"], "ACCEPTED")
        self.assertEqual(target["sigils"], ["ka", "vor", "shi", "thal", "nur"])
        self.assertEqual(len(target["native_mir_fingerprint"]), 64)
        self.assertEqual(len(target["typed_semantic_digest"]), 64)

    def test_vormir_curriculum_kills_old_epoch_before_successor_head(self):
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

    def test_morth_curriculum_forbids_dead_aevra_future(self):
        item = next(
            case
            for case in curriculum().cases
            if case.case_id == "n3-morth-has-no-living-future"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "MORTH")
        self.assertFalse(target["resurrection_allowed"])
        self.assertIn("no living future", target["reason"])

    def test_nur_curriculum_rotates_nyr_without_creating_authority(self):
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

    def test_survival_curriculum_rejects_khar_violating_branch(self):
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

    def test_bounded_autonomy_curriculum_is_proposal_only(self):
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
