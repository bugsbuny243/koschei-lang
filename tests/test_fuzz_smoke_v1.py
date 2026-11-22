"""A small, deterministic batch of each fuzzer on every pull request.

Larger runs: .github/workflows/fuzz.yml. The fuzzers are in tools/fuzz/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from koschei.packages_v1 import PackageError, load_lock

FUZZ = Path(__file__).resolve().parent.parent / "tools" / "fuzz"


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as out:
        return subprocess.run(
            [sys.executable, str(FUZZ / script), *args],
            capture_output=True,
            text=True,
            timeout=500,
            env=dict(os.environ, FUZZ_OUT=out),
        )


class FuzzSmokeTests(unittest.TestCase):
    def test_source_fuzz_check(self) -> None:
        result = run("source_fuzz.py", "11", "300", "check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_typed_program_fuzz(self) -> None:
        result = run("typed_program_fuzz.py", "11", "40")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_package_bytes_fuzz(self) -> None:
        result = run("package_bytes_fuzz.py", "11", "3000")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_package_format_fuzz(self) -> None:
        result = run("package_format_fuzz.py", "11", "5000")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


LOCK = {
    "schema": "koschei.packages-lock/v1",
    "packages": {
        "hexfmt": {
            "version": "1.2.0",
            "entry": "src/lib.ks",
            "source": {"path": "../hexfmt"},
            "digest": "a" * 64,
            "surface": [],
            "dependencies": [],
        }
    },
}


class FuzzFindingRegressionTests(unittest.TestCase):
    """Bugs the fuzzers found, kept fixed."""

    def load(self, **changes) -> None:
        payload = json.loads(json.dumps(LOCK))
        payload["packages"]["hexfmt"].update(changes)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "koschei.packages.lock.json").write_text(json.dumps(payload))
            load_lock(Path(directory))

    def test_valid_lock_loads(self) -> None:
        self.load()

    def test_unhashable_dependency_is_a_package_error(self) -> None:
        # Was: TypeError: unhashable type: 'list'
        for bad in ([[]], [{}]):
            with self.subTest(bad=bad), self.assertRaises(PackageError):
                self.load(dependencies=bad)

    def test_wrong_types_are_package_errors(self) -> None:
        for field, bad in (
            ("version", ["disk"]),
            ("entry", [{}]),
            ("source", "x"),
            ("source", {"path": 1}),
            ("source", {"git": "http://x", "rev": "a" * 40}),
        ):
            with self.subTest(field=field, bad=bad), self.assertRaises(PackageError):
                self.load(**{field: bad})

    def test_lock_entry_cannot_point_outside_the_package(self) -> None:
        for bad in ("../../etc/evil.ks", "/etc/evil.ks", "src/lib.txt"):
            with self.subTest(bad=bad), self.assertRaises(PackageError):
                self.load(entry=bad)


if __name__ == "__main__":
    unittest.main()
