"""The Koschei side of examples/supply_chain_demo behaves as its README says."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

DEMO = Path(__file__).resolve().parent.parent / "examples" / "supply_chain_demo" / "koschei"


def _with_helper(variant: str, command: str) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        shutil.copy(DEMO / "main.ks", base / "main.ks")
        shutil.copy(DEMO / f"{variant}.ks", base / "arrayref.ks")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main([command, str(base / "main.ks")])
        return code, out.getvalue(), err.getvalue()


class SupplyChainDemoTests(unittest.TestCase):
    def test_stealing_helper_does_not_compile(self) -> None:
        code, _, stderr = _with_helper("arrayref", "check")
        self.assertNotEqual(code, 0)
        self.assertIn("KS1101", stderr)

    def test_helper_asking_for_capabilities_does_not_compile(self) -> None:
        code, _, stderr = _with_helper("arrayref_asks", "check")
        self.assertNotEqual(code, 0)
        self.assertIn("KS1301", stderr)

    def test_honest_helper_is_pure(self) -> None:
        code, stdout, _ = _with_helper("arrayref_clean", "caps")
        self.assertEqual(code, 0)
        self.assertIn("no side-effect capability", stdout)
        code, stdout, _ = _with_helper("arrayref_clean", "run")
        self.assertEqual((code, stdout), (0, "true\n"))


if __name__ == "__main__":
    unittest.main()
