from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main


class LockedBuildTests(unittest.TestCase):
    def _project(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        source = root / "main.ks"
        helper = root / "helper.ks"
        lockfile = root / "koschei.lock.json"
        source.write_text(
            "import helper\n\nfn main() {\n    return\n}\n",
            encoding="utf-8",
        )
        helper.write_text("fn value() {\n    return\n}\n", encoding="utf-8")
        self.assertEqual(
            main(["lock", "create", str(source), "--output", str(lockfile)]),
            0,
        )
        return source, helper, lockfile

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_locked_build_verifies_before_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile = self._project(directory)
            binary = Path(directory) / "app"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--locked",
                        "--lockfile",
                        str(lockfile),
                        "--output",
                        str(binary),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(binary.is_file())
            self.assertIn("KOSCHEI BUILD", output.getvalue())

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_locked_build_stops_before_compilation_after_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, helper, lockfile = self._project(directory)
            binary = Path(directory) / "app"
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            error = io.StringIO()

            with redirect_stderr(error):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--locked",
                        "--lockfile",
                        str(lockfile),
                        "--output",
                        str(binary),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse(binary.exists())
            self.assertIn("KS1903", error.getvalue())
            self.assertIn("helper.ks", error.getvalue())

    def test_lockfile_argument_requires_locked_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "main.ks"
            source.write_text("fn main() {\n    return\n}\n", encoding="utf-8")
            error = io.StringIO()

            with redirect_stderr(error):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--lockfile",
                        str(Path(directory) / "koschei.lock.json"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("--lockfile requires --locked", error.getvalue())


if __name__ == "__main__":
    unittest.main()
