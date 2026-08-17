from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from koschei.model_curriculum import (
    ModelCurriculumError,
    build_model_curriculum,
    load_model_curriculum,
    verify_model_curriculum,
    write_model_curriculum,
)


class ModelCurriculumTests(unittest.TestCase):
    def make_repo(self, root: Path) -> str:
        (root / "docs").mkdir()
        (root / "examples").mkdir()
        (root / "README.md").write_text("# Koschei\n", encoding="utf-8")
        (root / "README.tr.md").write_text("# Koschei TR\n", encoding="utf-8")
        (root / "docs" / "reference.md").write_text(
            "Compiler truth comes before model output.\n",
            encoding="utf-8",
        )
        (root / "examples" / "hello.ks").write_text(
            'fn main() { println("hello") }\n',
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tests@koschei.invalid"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Koschei Tests"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_build_is_deterministic_and_compiler_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            first = build_model_curriculum(root, source_commit=commit)
            second = build_model_curriculum(root, source_commit=commit)

        self.assertEqual(first.curriculum_sha256, second.curriculum_sha256)
        self.assertEqual(first.case_count, 12)
        self.assertEqual(first.family_count, 12)
        self.assertEqual(first.accepted_count, 5)
        self.assertEqual(first.rejected_count, 7)
        self.assertEqual(
            first.level_counts,
            {"L0": 2, "L1": 6, "L2": 2, "L3": 1, "L4": 1},
        )
        self.assertEqual(
            first.diagnostic_distribution,
            {
                "KS1301": 1,
                "KS1306": 1,
                "KS2401": 2,
                "KS2402": 1,
                "KS2403": 1,
                "KS2404": 1,
            },
        )
        self.assertEqual(first.capability_distribution, {"disk": 1, "net": 3})

    def test_rejected_cases_have_exact_known_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            curriculum = build_model_curriculum(root, source_commit=commit)

        rejected = [case for case in curriculum.cases if case.outcome == "REJECTED"]
        self.assertTrue(rejected)
        self.assertTrue(all(case.diagnostic_code for case in rejected))
        self.assertTrue(all(case.capability_manifest is None for case in rejected))

    def test_accepted_cases_carry_mechanical_capability_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            curriculum = build_model_curriculum(root, source_commit=commit)

        by_id = {case.case_id: case for case in curriculum.cases}
        pure = by_id["l0-pure-arithmetic"]
        narrowed_net = by_id["l1-narrowed-net-token"]
        delegated_disk = by_id["l1-pass-narrow-disk-token"]

        self.assertEqual(pure.capability_manifest["domains"], [])
        self.assertEqual(narrowed_net.capability_manifest["domains"], ["net"])
        self.assertEqual(delegated_disk.capability_manifest["domains"], ["disk"])

    def test_tampered_source_is_rejected_by_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            curriculum = build_model_curriculum(root, source_commit=commit)
            payload = curriculum.to_dict()
            payload["cases"][0]["files"][0]["text"] += "tampered"

        with self.assertRaisesRegex(ModelCurriculumError, "source digest mismatch"):
            verify_model_curriculum(payload)

    def test_write_is_no_replace_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            curriculum = build_model_curriculum(root, source_commit=commit)
            output = root / "build" / "curriculum.json"
            write_model_curriculum(curriculum, output)
            loaded = load_model_curriculum(output)
            self.assertEqual(loaded.curriculum_sha256, curriculum.curriculum_sha256)
            with self.assertRaises(FileExistsError):
                write_model_curriculum(curriculum, output)

    def test_duplicate_json_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "curriculum.json"
            path.write_text(
                '{"schema_version":"one","schema_version":"two"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ModelCurriculumError, "duplicate JSON"):
                load_model_curriculum(path)

    def test_digest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            curriculum = build_model_curriculum(root, source_commit=commit)
            payload = json.loads(json.dumps(curriculum.to_dict()))
            payload["curriculum_sha256"] = "0" * 64

        with self.assertRaisesRegex(ModelCurriculumError, "digest mismatch"):
            verify_model_curriculum(payload)


if __name__ == "__main__":
    unittest.main()