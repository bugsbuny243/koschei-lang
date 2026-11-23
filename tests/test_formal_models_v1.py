"""TLA+ models in formal/tla.

The model check runs only when KOSCHEI_TLA2TOOLS points at tla2tools.jar and
java is installed (the `formal` workflow sets this up). The link test below
always runs: it fails if the implementation loses a check the model assumes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TLA = ROOT / "formal" / "tla"
JAR = os.environ.get("KOSCHEI_TLA2TOOLS")

# Each switch in PackageUpdate.cfg, the property that must break without it,
# and the code that implements it.
PACKAGE_CHECKS = {
    "CheckWidening": ("NoSilentWidening", "koschei/packages_v1.py", "raise SurfaceWidened(widened)"),
    "CheckSigner": ("SignerPinned", "koschei/packages_v1.py", "raise SignerChanged("),
    "CheckLog": ("HistoryMonotonic", "koschei/registry_v1.py", "refusing to trust the registry"),
    "CheckSurfaceClaim": ("IndexTruthful", "koschei/packages_v1.py", "but the compiler computes {list(surface)}; refusing it"),
}


def run_tlc(spec: str, cfg_text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(TLA / f"{spec}.tla", tmp)
        Path(tmp, "run.cfg").write_text(cfg_text, encoding="utf-8")
        result = subprocess.run(
            ["java", "-XX:+UseParallelGC", "-cp", str(JAR), "tlc2.TLC", "-workers", "auto",
             "-deadlock", "-metadir", str(Path(tmp, "states")), "-config", "run.cfg", f"{spec}.tla"],
            cwd=tmp, capture_output=True, text=True, timeout=1800,
        )
        return result.stdout + result.stderr


class ModelLinkTest(unittest.TestCase):
    def test_implementation_keeps_modelled_checks(self) -> None:
        cfg = (TLA / "PackageUpdate.cfg").read_text(encoding="utf-8")
        for switch, (_, path, needle) in PACKAGE_CHECKS.items():
            self.assertIn(f"{switch} = TRUE", cfg)
            self.assertIn(needle, (ROOT / path).read_text(encoding="utf-8"), f"{switch}: {path}")


@unittest.skipUnless(JAR and Path(JAR).is_file() and shutil.which("java"), "set KOSCHEI_TLA2TOOLS")
class PackageUpdateModelTest(unittest.TestCase):
    cfg = (TLA / "PackageUpdate.cfg").read_text(encoding="utf-8")

    def test_shipped_rule_holds(self) -> None:
        out = run_tlc("PackageUpdate", self.cfg)
        self.assertIn("No error has been found", out, out[-3000:])

    def test_policy_variant_holds(self) -> None:
        cfg = self.cfg.replace("Deny = {}", 'Deny = {"net"}').replace("RequireSigned = FALSE", "RequireSigned = TRUE")
        out = run_tlc("PackageUpdate", cfg)
        self.assertIn("No error has been found", out, out[-3000:])

    def test_every_check_is_load_bearing(self) -> None:
        for switch, (prop, _, _) in PACKAGE_CHECKS.items():
            with self.subTest(switch=switch):
                out = run_tlc("PackageUpdate", self.cfg.replace(f"{switch} = TRUE", f"{switch} = FALSE"))
                self.assertRegex(out, rf"(Invariant|Action property) {re.escape(prop)} is violated", out[-3000:])


if __name__ == "__main__":
    unittest.main()
