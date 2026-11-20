"""Packages v1, phase 2: the static registry, publish, add and the refusals."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.packages_v1 import PackageError, SurfaceWidened, sync
from koschei.registry_v1 import _similar, build_archive, extract_archive, publish, yank

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


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.base = Path(self._dir.name)
        self.registry = self.base / "registry"
        self.app = self.base / "app"
        (self.app / "src").mkdir(parents=True)
        (self.app / "koschei.toml").write_text(
            '[package]\nname = "app"\nversion = "0.1.0"\n\n'
            f'[registry]\nurl = "file://{self.registry}"\n'
        )
        (self.app / "src" / "main.ks").write_text(
            'import hexfmt\n\nfn main() {\n    println(hexfmt.pad("ff", 4))\n}\n'
        )

    def tearDown(self) -> None:
        self._dir.cleanup()

    def package(self, name: str, version: str, source: str, extra: str = "") -> Path:
        root = self.base / "src" / f"{name}-{version}"
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "koschei.toml").write_text(
            f'[package]\nname = "{name}"\nversion = "{version}"\nentry = "src/lib.ks"\n{extra}'
        )
        (root / "src" / "lib.ks").write_text(source)
        return root

    def depend(self, version: str) -> None:
        manifest = self.app / "koschei.toml"
        text = manifest.read_text()
        if "[dependencies]" in text:
            text = text.split("[dependencies]")[0]
        manifest.write_text(text + f'\n[dependencies]\nhexfmt = {{ version = "{version}" }}\n')

    def index(self, name: str = "hexfmt") -> dict:
        return json.loads((self.registry / "index" / f"{name}.json").read_text())

    def test_publish_add_run(self) -> None:
        published = publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        self.assertEqual(published.surface, ())
        code, out, err = ks("pkg", "add", "hexfmt@1.2.0", str(self.app))
        self.assertEqual(code, 0, err)
        self.assertIn("added     hexfmt 1.2.0: pure", out)
        self.assertIn('hexfmt = { version = "1.2.0" }', (self.app / "koschei.toml").read_text())
        self.assertEqual(ks("run", str(self.app / "src" / "main.ks"))[:2], (0, "00ff\n"))

    def test_versions_are_immutable(self) -> None:
        publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        with self.assertRaisesRegex(PackageError, "immutable"):
            publish(self.package("hexfmt", "1.2.0", WITH_NET), self.registry)

    def test_registry_update_that_adds_net_is_refused(self) -> None:
        publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        publish(self.package("hexfmt", "1.2.1", WITH_NET), self.registry)
        self.depend("1.2.0")
        sync(self.app)
        self.depend("1.2.1")
        with self.assertRaises(SurfaceWidened):
            sync(self.app)

    def test_index_that_lies_about_the_surface_is_refused(self) -> None:
        publish(self.package("hexfmt", "1.2.1", WITH_NET), self.registry)
        index = self.index()
        index["versions"][0]["surface"] = []
        (self.registry / "index" / "hexfmt.json").write_text(json.dumps(index))
        self.depend("1.2.1")
        with self.assertRaisesRegex(PackageError, "compiler computes"):
            sync(self.app)

    def test_swapped_archive_is_refused(self) -> None:
        publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        archive = self.registry / "archives" / "hexfmt" / "hexfmt-1.2.0.tar"
        archive.write_bytes(build_archive(self.package("hexfmt", "1.2.0", WITH_NET)))
        self.depend("1.2.0")
        with self.assertRaisesRegex(PackageError, "archive SHA-256"):
            sync(self.app)

    def test_yanked_version_is_not_installed_fresh_but_stays_locked(self) -> None:
        publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        self.depend("1.2.0")
        sync(self.app)
        yank(self.registry, "hexfmt", "1.2.0")
        sync(self.app)  # already locked: still installs
        (self.app / "koschei.packages.lock.json").unlink()
        with self.assertRaisesRegex(PackageError, "yanked"):
            sync(self.app)

    def test_look_alike_names_are_held(self) -> None:
        publish(self.package("hexfmt", "1.2.0", PURE), self.registry)
        for name in ("hexfnt", "hexmft", "hex_fmt", "hexfmtt"):
            with self.subTest(name=name), self.assertRaisesRegex(PackageError, "held for review"):
                publish(self.package(name, "1.0.0", PURE), self.registry)
        publish(self.package("hexfnt", "1.0.0", PURE), self.registry, allow_similar_name=True)
        self.assertFalse(_similar("hexfmt", "base64"))

    def test_registry_package_cannot_depend_on_a_path(self) -> None:
        root = self.package("hexfmt", "1.2.0", PURE, '\n[dependencies]\nleaf = { path = "../leaf" }\n')
        with self.assertRaisesRegex(PackageError, "must come from the registry"):
            publish(root, self.registry)

    def test_registry_dependencies_resolve_transitively(self) -> None:
        publish(self.package("leaf", "0.1.0", "fn one() -> Int {\n    return 1\n}\n"), self.registry)
        publish(
            self.package("hexfmt", "1.2.0", PURE, '\n[dependencies]\nleaf = { version = "0.1.0" }\n'),
            self.registry,
        )
        self.assertEqual(self.index()["versions"][0]["dependencies"], {"leaf": "0.1.0"})
        self.depend("1.2.0")
        result = sync(self.app)
        self.assertEqual(sorted(c.name for c in result.changes), ["hexfmt", "leaf"])

    def test_archive_extraction_refuses_unsafe_entries(self) -> None:
        def tar_with(info: tarfile.TarInfo, data: bytes = b"") -> bytes:
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w") as archive:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            return buffer.getvalue()

        cases = {
            "traversal": tar_with(tarfile.TarInfo("../evil.ks"), b"x"),
            "absolute": tar_with(tarfile.TarInfo("/etc/evil.ks"), b"x"),
            "script": tar_with(tarfile.TarInfo("build.sh"), b"x"),
        }
        link = tarfile.TarInfo("src/lib.ks")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        cases["symlink"] = tar_with(link)
        for label, data in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(PackageError):
                    extract_archive(data, Path(directory))

    def test_archives_are_deterministic(self) -> None:
        root = self.package("hexfmt", "1.2.0", PURE)
        self.assertEqual(
            hashlib.sha256(build_archive(root)).hexdigest(),
            hashlib.sha256(build_archive(root)).hexdigest(),
        )


class RegistryServerTests(unittest.TestCase):
    def test_registry_paths_are_strict(self) -> None:
        import importlib.util
        import sys

        path = Path(__file__).resolve().parent.parent / "server" / "playground" / "app.py"
        spec = importlib.util.spec_from_file_location("playground_app_registry", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        pattern = module.REGISTRY_PATH
        self.assertTrue(pattern.fullmatch("/registry/index/hexfmt.json"))
        self.assertTrue(pattern.fullmatch("/registry/archives/hexfmt/hexfmt-1.2.0.tar"))
        for bad in (
            "/registry/index/../app.py",
            "/registry/archives/hexfmt/other-1.2.0.tar",
            "/registry/archives/hexfmt/hexfmt-1.2.0.tar/x",
            "/registry/README.md",
            "/registry/index/Hex.json",
        ):
            self.assertIsNone(pattern.fullmatch(bad), bad)


if __name__ == "__main__":
    unittest.main()
