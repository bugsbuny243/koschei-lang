"""Two builds of the same source are byte-identical, wherever they run.

The Go workspace is a fresh temporary directory; without -trimpath and an
empty build id its path was embedded and every build differed.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

APP = Path(__file__).resolve().parent.parent / "examples" / "apps" / "release_gate" / "main.ks"


@unittest.skipIf(shutil.which("go") is None, "Go toolchain is not installed")
class NativeReproducibleBuildTests(unittest.TestCase):
    def build(self, source: Path, target: Path) -> str:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(source), "-o", str(target)]), 0, errors.getvalue())
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def test_builds_from_different_directories_are_identical(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            copy = Path(second) / "elsewhere" / "main.ks"
            copy.parent.mkdir()
            shutil.copy(APP, copy)
            digests = {
                self.build(APP, Path(first) / "a"),
                self.build(APP, Path(first) / "b"),
                self.build(copy, Path(second) / "c"),
            }
        self.assertEqual(len(digests), 1)


if __name__ == "__main__":
    unittest.main()
