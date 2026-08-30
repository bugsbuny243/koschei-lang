from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify_solohost_artifact_v1.py"


class SoloHostArtifactPolicyV1Tests(unittest.TestCase):
    def _run(self, artifact: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFIER), str(artifact)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_accepts_minimal_source_free_artifact_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)
            (artifact / "ks").write_bytes(b"sealed-executable-placeholder")
            (artifact / "koschei-release-manifest.json").write_text("{}\n", encoding="utf-8")

            result = self._run(artifact)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("KOSCHEI SOLOHOST ARTIFACT: PASS", result.stdout)

    def test_rejects_python_source_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)
            (artifact / "ks").write_bytes(b"sealed-executable-placeholder")
            (artifact / "koschei-release-manifest.json").write_text("{}\n", encoding="utf-8")
            leaked = artifact / "koschei"
            leaked.mkdir()
            (leaked / "compiler.py").write_text("print('private source')\n", encoding="utf-8")

            result = self._run(artifact)

            self.assertEqual(result.returncode, 1)
            self.assertIn("KOSCHEI SOLOHOST ARTIFACT: REJECTED", result.stdout)
            self.assertIn("forbidden source suffix .py", result.stdout)

    def test_rejects_private_repository_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)
            (artifact / "ks").write_bytes(b"sealed-executable-placeholder")
            (artifact / "koschei-release-manifest.json").write_text("{}\n", encoding="utf-8")
            git_dir = artifact / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("private\n", encoding="utf-8")

            result = self._run(artifact)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden private/source path component", result.stdout)


if __name__ == "__main__":
    unittest.main()
