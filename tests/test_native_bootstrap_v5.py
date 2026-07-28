from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
class NativeBootstrapV5Tests(unittest.TestCase):
    def test_native_bootstrap_suite(self) -> None:
        result = subprocess.run(
            ["go", "test", "./..."],
            cwd=ROOT / "native",
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
