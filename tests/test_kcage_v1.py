"""Run the kcage prototype's Go tests (they skip where the kernel lacks support)."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest

CAGE = Path(__file__).resolve().parent.parent / "cage"


@unittest.skipUnless(shutil.which("go"), "go not installed")
class KcageTests(unittest.TestCase):
    def test_go_tests_pass(self) -> None:
        result = subprocess.run(
            ["go", "test", "-count=1", "./..."],
            cwd=CAGE,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
