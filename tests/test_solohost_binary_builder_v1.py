from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_solohost_binary_v1.py"


class SoloHostBinaryBuilderV1Tests(unittest.TestCase):
    def _run(self, *extra: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--output",
                    str(Path(tmp) / "out"),
                    *extra,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_rejects_include_data_dir_before_nuitka_execution(self) -> None:
        result = self._run("--nuitka-arg=--include-data-dir=.=payload")
        self.assertEqual(result.returncode, 2)
        self.assertIn("data-inclusion option is forbidden", result.stderr)

    def test_rejects_include_data_files_before_nuitka_execution(self) -> None:
        result = self._run("--nuitka-arg=--include-data-files=native/datajson/json.go=json.go")
        self.assertEqual(result.returncode, 2)
        self.assertIn("data-inclusion option is forbidden", result.stderr)

    def test_rejects_output_override(self) -> None:
        result = self._run("--nuitka-arg=--output-dir=/tmp/escape")
        self.assertEqual(result.returncode, 2)
        self.assertIn("output option cannot be overridden", result.stderr)

    def test_rejects_mode_override(self) -> None:
        result = self._run("--nuitka-arg=--mode=onefile")
        self.assertEqual(result.returncode, 2)
        self.assertIn("mode cannot be overridden", result.stderr)


if __name__ == "__main__":
    unittest.main()
