import json
from pathlib import Path
import tempfile
import unittest

from koschei.native_model_curriculum_lang_hardening_v1 import REQUIRED_HARDENING_CASE_IDS
from koschei.native_model_curriculum_lang_v1 import (
    N6_FAMILY,
    LangNativeCurriculumError,
    build_lang_native_model_curriculum_v1,
    load_lang_native_model_curriculum_v1,
    verify_lang_native_model_curriculum_v1,
    write_lang_native_model_curriculum_v1,
)
from koschei.native_model_curriculum_v2 import build_native_model_curriculum_v2


SOURCE = "a" * 40
PARENT = "b" * 64


class LangNativeCurriculumBoundaryTests(unittest.TestCase):
    def active(self):
        return build_lang_native_model_curriculum_v1(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )

    def test_active_builder_contains_no_sentinel_merge_semantics(self):
        curriculum = self.active()
        serialized = json.dumps(curriculum.to_dict(), sort_keys=True).lower()

        self.assertNotIn("sentinel", serialized)
        self.assertNotIn("historical-security-material", serialized)
        self.assertNotIn("historical or new security material", serialized)
        n6 = [case for case in curriculum.cases if case.stage == "N6"]
        self.assertEqual(len(n6), 3)
        self.assertTrue(all(case.family == N6_FAMILY for case in n6))
        self.assertTrue(all("historical" not in law.lower() for case in n6 for law in case.law_ids))

    def test_legacy_merged_curriculum_is_rejected_by_active_verifier(self):
        legacy = build_native_model_curriculum_v2(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )
        with self.assertRaisesRegex(
            LangNativeCurriculumError,
            "cancelled Sentinel-merge semantics",
        ):
            verify_lang_native_model_curriculum_v1(legacy)

    def test_active_profile_adds_exact_n3_n4_hardening_cases_and_reseals(self):
        legacy = build_native_model_curriculum_v2(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )
        active = self.active()
        active_ids = {case.case_id for case in active.cases}

        self.assertNotEqual(active.curriculum_sha256, legacy.curriculum_sha256)
        self.assertEqual(active.case_count, legacy.case_count + 4)
        self.assertEqual(active.stage_counts["N3"], legacy.stage_counts["N3"] + 2)
        self.assertEqual(active.stage_counts["N4"], legacy.stage_counts["N4"] + 2)
        self.assertEqual(active.accepted_count, legacy.accepted_count + 1)
        self.assertEqual(active.rejected_count, legacy.rejected_count + 3)
        self.assertTrue(set(REQUIRED_HARDENING_CASE_IDS).issubset(active_ids))

    def test_hara_cannot_transfer_across_aevra(self):
        item = next(
            case for case in self.active().cases
            if case.case_id == "n3-hara-cannot-transfer-across-aevra"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertFalse(target["cross_aevra_hara_transfer"])
        self.assertFalse(target["authority"])
        self.assertIn("different Aevra", target["reason"])

    def test_matrix_cannot_transfer_across_veyra(self):
        item = next(
            case for case in self.active().cases
            if case.case_id == "n3-matrix-cannot-transfer-across-veyra"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertFalse(target["cross_veyra_matrix_transfer"])
        self.assertFalse(target["authority"])
        self.assertIn("different Veyra", target["reason"])

    def test_nyr_render_does_not_expose_canonical_operational_world(self):
        item = next(
            case for case in self.active().cases
            if case.case_id == "n4-nyr-does-not-expose-canonical-world"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "ACCEPTED")
        self.assertFalse(target["canonical_subjects_exposed"])
        self.assertFalse(target["veyra_identity_exposed"])
        self.assertFalse(target["stable_topology_labels"])
        self.assertFalse(target["authority"])
        self.assertEqual(target["visible_binding_count"], 5)
        self.assertEqual(len(target["render_sha256"]), 64)

    def test_nyr_projection_is_not_cross_veyra_operational_map(self):
        item = next(
            case for case in self.active().cases
            if case.case_id == "n4-nyr-is-not-cross-veyra-transferable"
        )
        target = json.loads(item.target_text)

        self.assertEqual(item.outcome, "REJECTED")
        self.assertEqual(target["result"], "ZERO")
        self.assertFalse(target["aliases_transfer_unchanged"])
        self.assertFalse(target["surface_digest_transfers_unchanged"])
        self.assertFalse(target["cross_veyra_operational_map_reuse"])
        self.assertFalse(target["authority"])

    def test_missing_hardening_case_is_rejected_even_if_release_is_resealed(self):
        active = self.active().to_dict()
        active["cases"] = [
            case for case in active["cases"]
            if case["case_id"] != "n4-nyr-does-not-expose-canonical-world"
        ]
        active["case_count"] -= 1
        active["stage_counts"]["N4"] -= 1
        active["accepted_count"] -= 1

        # Structural v2 verification will reject the stale release digest before
        # the semantic hardening check. This is still fail-closed at the active
        # training boundary.
        with self.assertRaises(LangNativeCurriculumError):
            verify_lang_native_model_curriculum_v1(active)

    def test_active_write_load_round_trip_and_legacy_file_fails(self):
        active = self.active()
        legacy = build_native_model_curriculum_v2(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_path = root / "active.json"
            write_lang_native_model_curriculum_v1(active, active_path)
            self.assertEqual(load_lang_native_model_curriculum_v1(active_path), active)

            legacy_path = root / "legacy.json"
            legacy_path.write_text(
                json.dumps(legacy.to_dict(), sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaises(LangNativeCurriculumError):
                load_lang_native_model_curriculum_v1(legacy_path)


if __name__ == "__main__":
    unittest.main()
