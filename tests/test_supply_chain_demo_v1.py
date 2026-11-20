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

    def test_compromised_update_is_refused_by_pkg_sync(self) -> None:
        from koschei.packages_v1 import SurfaceWidened, sync

        update = DEMO / "update"
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shutil.copytree(update / "app", base / "app")
            shutil.copytree(update / "arrayref-0.3.9", base / "arrayref")
            result = sync(base / "app")
            self.assertEqual([(c.name, c.surface) for c in result.changes], [("arrayref", ())])
            shutil.rmtree(base / "arrayref")
            shutil.copytree(update / "arrayref-0.3.10", base / "arrayref")
            with self.assertRaises(SurfaceWidened) as caught:
                sync(base / "app")
            self.assertEqual(caught.exception.changes[0].added_capabilities, ("disk", "net"))
            code, stdout, _ = _run_in(base / "app" / "src" / "main.ks")
            self.assertEqual((code, stdout), (0, "true\n"))


def _run_in(path: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(["run", str(path)])
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
