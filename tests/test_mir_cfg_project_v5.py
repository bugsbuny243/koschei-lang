from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MirCfgProjectTests(unittest.TestCase):
    def test_real_project_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "koschei", "run", str(ROOT / "examples" / "mir_cfg_project.ks")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "large")

    def test_supply_chain_attack_is_rejected(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "koschei", "check", str(ROOT / "examples" / "supply_chain" / "main.ks")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KS2401", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
