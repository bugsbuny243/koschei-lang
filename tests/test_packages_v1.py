"""Packages v1, phase 1: pinned dependencies with locked capability surfaces."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.packages_v1 import (
    LOCK_NAME,
    PackageError,
    SurfaceWidened,
    parse_dependencies,
    sync,
)

PURE = """fn pad(text: String, width: Int) -> String {
    let mut out = text
    while out.length() < width {
        out = "0{out}"
    }
    return out
}
"""
WITH_NET = PURE.replace("width: Int)", "width: Int, net: NetCaps)")


def ks(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(list(argv))
    return code, out.getvalue(), err.getvalue()


class PackagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.base = Path(self._dir.name)
        self.package("hexfmt", "1.2.0", PURE)
        self.app = self.base / "app"
        (self.app / "src").mkdir(parents=True)
        (self.app / "koschei.toml").write_text(
            '[package]\nname = "app"\nversion = "0.1.0"\n\n'
            '[dependencies]\nhexfmt = { path = "../hexfmt" }\n'
        )
        (self.app / "src" / "main.ks").write_text(
            'import hexfmt\n\nfn main() {\n    println(hexfmt.pad("ff", 4))\n}\n'
        )

    def tearDown(self) -> None:
        self._dir.cleanup()

    def package(self, name: str, version: str, source: str, extra: str = "") -> Path:
        root = self.base / name
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "koschei.toml").write_text(
            f'[package]\nname = "{name}"\nversion = "{version}"\nentry = "src/lib.ks"\n{extra}'
        )
        (root / "src" / "lib.ks").write_text(source)
        return root

    def run_app(self) -> tuple[int, str, str]:
        return ks("run", str(self.app / "src" / "main.ks"))

    def test_unsynced_project_does_not_compile(self) -> None:
        code, _, err = self.run_app()
        self.assertNotEqual(code, 0)
        self.assertIn("KS1606", err)
        self.assertIn("ks pkg sync", err)

    def test_pure_package_runs_and_is_reported_pure(self) -> None:
        code, out, _ = ks("pkg", "sync", str(self.app))
        self.assertEqual(code, 0)
        self.assertIn("hexfmt 1.2.0: pure", out)
        self.assertEqual(self.run_app()[:2], (0, "00ff\n"))
        lock = json.loads((self.app / LOCK_NAME).read_text())
        self.assertEqual(lock["packages"]["hexfmt"]["surface"], [])
        code, out, _ = ks("caps", str(self.app / "src" / "main.ks"))
        self.assertIn("pure computation", out)

    def test_update_adding_a_capability_is_refused_until_allowed(self) -> None:
        sync(self.app)
        self.package("hexfmt", "1.2.1", WITH_NET)
        code, _, err = ks("pkg", "sync", str(self.app))
        self.assertEqual(code, 3)
        self.assertIn("hexfmt 1.2.1 adds: net", err)
        self.assertIn("--allow net", err)
        # Nothing changed: the locked pure version still builds.
        self.assertEqual(self.run_app()[:2], (0, "00ff\n"))
        code, out, _ = ks("pkg", "sync", "--allow", "net", str(self.app))
        self.assertEqual(code, 0)
        self.assertIn("updated   hexfmt 1.2.1: net", out)
        # The app must now pass the token itself.
        code, _, err = self.run_app()
        self.assertNotEqual(code, 0)
        self.assertIn("KS1301", err)

    def test_transitive_widening_is_refused(self) -> None:
        self.package("hexfmt", "1.2.0", PURE, '\n[dependencies]\nleaf = { path = "../leaf" }\n')
        self.package("leaf", "0.1.0", "fn one() -> Int {\n    return 1\n}\n")
        result = sync(self.app)
        self.assertEqual({c.name: c.surface for c in result.changes}, {"hexfmt": (), "leaf": ()})
        self.package("leaf", "0.2.0", "fn one(disk: DiskCaps) -> Int {\n    return 1\n}\n")
        with self.assertRaises(SurfaceWidened) as caught:
            sync(self.app)
        names = {change.name for change in caught.exception.changes}
        self.assertEqual(names, {"leaf"})

    def test_surface_counts_imported_dependencies_not_declared_ones(self) -> None:
        self.package("hexfmt", "1.2.0", PURE, '\n[dependencies]\nleaf = { path = "../leaf" }\n')
        self.package("leaf", "0.1.0", "fn one(disk: DiskCaps) -> Int {\n    return 1\n}\n")
        result = sync(self.app)
        surfaces = {c.name: c.surface for c in result.changes}
        self.assertEqual(surfaces["leaf"], ("disk",))
        # Declared but not imported: hexfmt cannot reach leaf, so it stays pure;
        # leaf's own entry still shows and guards its surface.
        self.assertEqual(surfaces["hexfmt"], ())
        self.package(
            "hexfmt", "1.3.0",
            "import leaf\n\nfn two(disk: DiskCaps) -> Int {\n    return leaf.one(disk) + 1\n}\n",
            '\n[dependencies]\nleaf = { path = "../leaf" }\n',
        )
        with self.assertRaises(SurfaceWidened) as caught:
            sync(self.app)
        self.assertEqual([c.name for c in caught.exception.changes], ["hexfmt"])

    def test_tampered_vendored_package_does_not_compile(self) -> None:
        sync(self.app)
        vendored = next((self.app / ".koschei" / "packages").glob("hexfmt-*"))
        lib = vendored / "src" / "lib.ks"
        lib.write_text(lib.read_text().replace('"0{out}"', '"1{out}"'))
        code, _, err = self.run_app()
        self.assertNotEqual(code, 0)
        self.assertIn("changed after it was locked", err)

    def test_policy_deny_wins_over_allow(self) -> None:
        self.package("hexfmt", "1.2.0", WITH_NET)
        with (self.app / "koschei.toml").open("a") as manifest:
            manifest.write('\n[policy]\ndeny = ["net"]\n')
        code, _, err = ks("pkg", "sync", "--allow", "net", str(self.app))
        self.assertEqual(code, 1)
        self.assertIn("[policy] deny", err)
        self.assertFalse((self.app / LOCK_NAME).exists())

    def test_declared_surface_must_match_computed(self) -> None:
        self.package("hexfmt", "1.2.0", WITH_NET, "surface = []\n")
        with self.assertRaisesRegex(PackageError, "compiler computes"):
            sync(self.app)

    def test_package_cannot_take_root_authority(self) -> None:
        self.package("hexfmt", "1.2.0", 'fn main(caps: SystemCaps) {\n    println("x")\n}\n')
        with self.assertRaisesRegex(PackageError, "SystemCaps"):
            sync(self.app)

    def test_only_direct_dependencies_are_importable(self) -> None:
        self.package("hexfmt", "1.2.0", PURE, '\n[dependencies]\nleaf = { path = "../leaf" }\n')
        self.package("leaf", "0.1.0", "fn one() -> Int {\n    return 1\n}\n")
        sync(self.app)
        (self.app / "src" / "main.ks").write_text("import leaf\n\nfn main() {\n    println(leaf.one())\n}\n")
        code, _, err = self.run_app()
        self.assertNotEqual(code, 0)
        self.assertIn("KS1606", err)

    def test_manifest_edit_without_sync_is_refused(self) -> None:
        sync(self.app)
        manifest = self.app / "koschei.toml"
        manifest.write_text(manifest.read_text().replace("../hexfmt", "../other"))
        code, _, err = self.run_app()
        self.assertNotEqual(code, 0)
        self.assertIn("does not match", err)

    def test_package_files_are_sources_only(self) -> None:
        root = self.base / "hexfmt"
        (root / "build.sh").write_text("#!/bin/sh\necho pwned\n")
        sync(self.app)
        vendored = next((self.app / ".koschei" / "packages").glob("hexfmt-*"))
        self.assertEqual(
            sorted(p.relative_to(vendored).as_posix() for p in vendored.rglob("*") if p.is_file()),
            ["koschei.toml", "src/lib.ks"],
        )

    def test_dependency_specs_reject_moving_refs(self) -> None:
        with self.assertRaisesRegex(PackageError, "40-character"):
            parse_dependencies({"dependencies": {"x": {"git": "https://example.com/x", "rev": "main"}}}, "t")
        with self.assertRaisesRegex(PackageError, "https"):
            parse_dependencies({"dependencies": {"x": {"git": "git@example.com:x", "rev": "a" * 40}}}, "t")
        with self.assertRaises(PackageError):
            parse_dependencies({"dependencies": {"x": {"path": "a", "git": "https://e/x"}}}, "t")

    def test_native_build_uses_the_locked_package(self) -> None:
        import shutil

        if shutil.which("go") is None:
            raise unittest.SkipTest("go is not installed")
        sync(self.app)
        binary = self.base / "appbin"
        code, _, err = ks("build", str(self.app / "src" / "main.ks"), "--output", str(binary))
        self.assertEqual(code, 0, err)
        import subprocess

        self.assertEqual(subprocess.run([str(binary)], capture_output=True, text=True).stdout, "00ff\n")


if __name__ == "__main__":
    unittest.main()
