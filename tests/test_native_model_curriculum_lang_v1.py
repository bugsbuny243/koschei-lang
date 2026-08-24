import json
from pathlib import Path
import tempfile
import unittest

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
    def test_active_builder_contains_no_sentinel_merge_semantics(self):
        curriculum = build_lang_native_model_curriculum_v1(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )
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

    def test_active_profile_reseals_curriculum_after_n6_rewrite(self):
        legacy = build_native_model_curriculum_v2(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )
        active = build_lang_native_model_curriculum_v1(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )

        self.assertNotEqual(active.curriculum_sha256, legacy.curriculum_sha256)
        self.assertEqual(active.case_count, legacy.case_count)
        self.assertEqual(active.stage_counts, legacy.stage_counts)
        self.assertEqual(active.accepted_count, legacy.accepted_count)
        self.assertEqual(active.rejected_count, legacy.rejected_count)

    def test_active_write_load_round_trip_and_legacy_file_fails(self):
        active = build_lang_native_model_curriculum_v1(
            source_commit=SOURCE,
            parent_curriculum_digest=PARENT,
        )
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
