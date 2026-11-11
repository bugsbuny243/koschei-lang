from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from koschei.model_curriculum import ModelCurriculumError
from koschei.model_curriculum_cli import verify_trusted_checkout


class ModelCurriculumCliTests(unittest.TestCase):
    def make_repo(self, root: Path) -> str:
        (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
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

    def test_clean_exact_checkout_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            verify_trusted_checkout(root, commit)

    def test_wrong_commit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            with self.assertRaisesRegex(ModelCurriculumError, "does not match"):
                verify_trusted_checkout(root, "0" * 40)

    def test_dirty_tracked_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(ModelCurriculumError, "completely clean"):
                verify_trusted_checkout(root, commit)

    def test_untracked_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.make_repo(root)
            (root / "untracked.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(ModelCurriculumError, "completely clean"):
                verify_trusted_checkout(root, commit)


if __name__ == "__main__":
    unittest.main()
