"""The download sold on Polar: what it holds, that it is deterministic, and
that the Koschei inside it runs the README's commands."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.polar_bundle_v1 import ROOT, build_bundle, version

TOP_LEVEL = {
    "LICENSE",
    "LICENSE.tr.md",
    "LICENSING.md",
    "LICENSING.tr.md",
    "README.md",
    "README.tr.md",
    "RELEASE_NOTES.md",
    "RELEASE_NOTES.tr.md",
    "docs",
    "examples",
    "install.sh",
    "koschei",
    "native",
    "pyproject.toml",
}


class PolarBundleTests(unittest.TestCase):
    def build(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-polar-test-")
        self.addCleanup(temporary.cleanup)
        return build_bundle(Path(temporary.name))

    def test_bundle_holds_the_product_and_nothing_internal(self) -> None:
        bundle = self.build()
        prefix = f"koschei-lang-{version()}/"
        self.assertEqual(bundle.name, f"koschei-lang-{version()}.zip")
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
            self.assertTrue(all(name.startswith(prefix) for name in names))
            relative = [name[len(prefix):] for name in names]
            self.assertEqual({name.split("/")[0] for name in relative}, TOP_LEVEL)
            self.assertFalse([name for name in relative if "__pycache__" in name or name.endswith(".pyc")])
            for required in (
                "koschei/__main__.py",
                "koschei/core_library/text.ks",
                "native/datajson/json.go",
                "docs/guide/LANGUAGE_GUIDE.en.md",
                "docs/reference/ERROR_CODES.md",
                "examples/apps/wordfreq/main.ks",
            ):
                self.assertIn(required, relative)
            self.assertEqual(archive.getinfo(prefix + "install.sh").external_attr >> 16 & 0o777, 0o755)
            self.assertEqual(
                archive.read(prefix + "README.md"),
                (ROOT / "distribution/polar/README.md").read_bytes(),
            )
            self.assertEqual(archive.read(prefix + "LICENSE"), (ROOT / "LICENSE").read_bytes())

    def test_bundle_is_deterministic(self) -> None:
        self.assertEqual(self.build().read_bytes(), self.build().read_bytes())

    def test_the_bundled_koschei_runs_the_readme_commands(self) -> None:
        bundle = self.build()
        with tempfile.TemporaryDirectory(prefix="koschei-polar-run-") as directory:
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(directory)
            home = Path(directory) / f"koschei-lang-{version()}"
            environment = dict(os.environ, PYTHONPATH=str(home))

            def ks(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, "-m", "koschei", *arguments], cwd=home, env=environment,
                    capture_output=True, text=True, timeout=120, check=False,
                )

            located = subprocess.run(
                [sys.executable, "-c", "import koschei; print(koschei.__file__)"],
                cwd=home, env=environment, capture_output=True, text=True, check=True,
            )
            self.assertTrue(Path(located.stdout.strip()).is_relative_to(home))
            hello = ks("run", "examples/hello.ks")
            self.assertEqual((hello.returncode, hello.stdout), (0, "Koschei\n1\n"))
            rejected = ks("check", "examples/supply_chain/main.ks")
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("KS2401", rejected.stdout + rejected.stderr)

    def test_english_and_turkish_price_tables_agree(self) -> None:
        def prices(name: str) -> list[str]:
            return re.findall(r"\*\*(\d+) USD\*\*", (ROOT / name).read_text(encoding="utf-8"))

        self.assertEqual(prices("LICENSING.md"), ["49"])
        self.assertEqual(prices("LICENSING.tr.md"), prices("LICENSING.md"))


if __name__ == "__main__":
    unittest.main()
