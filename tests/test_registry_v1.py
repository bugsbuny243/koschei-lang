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
from koschei.registry_v1 import _similar, build_archive, extract_archive, keygen
from koschei.registry_v1 import publish as _publish
from koschei.packages_v1 import SignerChanged
from koschei.registry_v1 import _append_log, _log_event, load_key, parse_log, sign_existing, yank

_KEYS: dict[str, Path] = {}


def publish(root, registry, **options):
    """Publish with a per-registry test key unless a key is given."""

    if "key" not in options:
        key = _KEYS.get(str(registry))
        if key is None:
            key = Path(registry).parent / "test.key"
            if not key.exists():
                keygen(key)
            _KEYS[str(registry)] = key
        options["key"] = key
    return _publish(root, registry, **options)

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
        # The signature covers the surface, so the edit is caught there first.
        with self.assertRaisesRegex(PackageError, "signature does not verify|compiler computes"):
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


class SignatureAndLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.base = Path(self._dir.name)
        self.registry = self.base / "registry"
        self.key_a = self.base / "a.key"
        self.key_b = self.base / "b.key"
        self.signer_a = keygen(self.key_a)
        self.signer_b = keygen(self.key_b)
        self.app = self.base / "app"
        (self.app / "src").mkdir(parents=True)
        (self.app / "src" / "main.ks").write_text(
            'import hexfmt\n\nfn main() {\n    println(hexfmt.pad("ff", 4))\n}\n'
        )
        self.manifest("1.0.0")

    def tearDown(self) -> None:
        self._dir.cleanup()

    def manifest(self, version: str, extra: str = "") -> None:
        (self.app / "koschei.toml").write_text(
            '[package]\nname = "app"\nversion = "0.1.0"\n\n'
            f'[registry]\nurl = "file://{self.registry}"\n\n{extra}'
            f'[dependencies]\nhexfmt = {{ version = "{version}" }}\n'
        )

    def package(self, version: str) -> Path:
        root = self.base / "src" / version
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "koschei.toml").write_text(
            f'[package]\nname = "hexfmt"\nversion = "{version}"\nentry = "src/lib.ks"\n'
        )
        (root / "src" / "lib.ks").write_text(PURE)
        return root

    def index(self) -> dict:
        return json.loads((self.registry / "index" / "hexfmt.json").read_text())

    def write_index(self, index: dict) -> None:
        (self.registry / "index" / "hexfmt.json").write_text(json.dumps(index))

    def test_publish_signs_sets_owner_and_logs(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        index = self.index()
        self.assertEqual(index["owners"], [self.signer_a])
        self.assertEqual(index["versions"][0]["signer"], self.signer_a)
        events = parse_log((self.registry / "log.jsonl").read_bytes())
        self.assertEqual([(e["event"], e["name"], e["version"]) for e in events], [("publish", "hexfmt", "1.0.0")])
        result = sync(self.app)
        self.assertEqual(result.lock.packages["hexfmt"]["signer"], self.signer_a)
        self.assertEqual(result.lock.registry_log[f"file://{self.registry}"]["seq"], 0)

    def test_non_owner_cannot_publish(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        with self.assertRaisesRegex(PackageError, "not an owner"):
            _publish(self.package("1.0.1"), self.registry, key=self.key_b)

    def test_forged_signature_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        index = self.index()
        signature = index["versions"][0]["signature"]
        index["versions"][0]["signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
        self.write_index(index)
        with self.assertRaisesRegex(PackageError, "signature does not verify"):
            sync(self.app)

    def test_signer_change_is_refused_until_allowed(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        sync(self.app)
        # A compromised registry adds its own key as owner and signs a new version.
        index = self.index()
        index["owners"] = [self.signer_b]
        self.write_index(index)
        _publish(self.package("1.0.1"), self.registry, key=self.key_b)
        self.manifest("1.0.1")
        with self.assertRaises(SignerChanged):
            sync(self.app)
        result = sync(self.app, allow_new_signer=frozenset({"hexfmt"}))
        self.assertEqual(result.lock.packages["hexfmt"]["signer"], self.signer_b)

    def test_rewritten_log_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        _publish(self.package("1.0.1"), self.registry, key=self.key_a)
        self.manifest("1.0.1")
        sync(self.app)
        # Rewrite history: drop the first event and rebuild the chain.
        log = self.registry / "log.jsonl"
        events = parse_log(log.read_bytes())
        log.unlink()
        for event in events[1:]:
            _append_log(self.registry, {k: v for k, v in event.items() if k not in {"seq", "prev", "_hash"}})
        with self.assertRaisesRegex(PackageError, "no longer contains the history"):
            sync(self.app)

    def test_index_that_hides_a_logged_yank_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        yank(self.registry, "hexfmt", "1.0.0")
        index = self.index()
        for entry in index["versions"]:
            entry["yanked"] = False
        self.write_index(index)
        with self.assertRaisesRegex(PackageError, "disagree on yanked"):
            sync(self.app)

    def test_index_that_invents_a_yank_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        sync(self.app)
        index = self.index()
        for entry in index["versions"]:
            entry["yanked"] = True
        self.write_index(index)
        with self.assertRaisesRegex(PackageError, "disagree on yanked"):
            sync(self.app)

    def test_honest_yank_keeps_the_locked_version(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        sync(self.app)
        yank(self.registry, "hexfmt", "1.0.0")
        sync(self.app)
        (self.app / "koschei.packages.lock.json").unlink()
        with self.assertRaisesRegex(PackageError, "is yanked"):
            sync(self.app)

    def test_entry_missing_from_log_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        (self.registry / "log.jsonl").write_bytes(b"")
        with self.assertRaisesRegex(PackageError, "not in the registry's public log"):
            sync(self.app)

    def test_broken_chain_is_refused(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        _publish(self.package("1.0.1"), self.registry, key=self.key_a)
        log = self.registry / "log.jsonl"
        lines = log.read_bytes().splitlines(keepends=True)
        log.write_bytes(lines[1] + lines[0])
        with self.assertRaisesRegex(PackageError, "breaks the chain"):
            sync(self.app)

    def test_unsigned_legacy_entry_and_require_signed(self) -> None:
        _publish(self.package("1.0.0"), self.registry, key=self.key_a)
        index = self.index()
        entry = index["versions"][0]
        del entry["signer"], entry["signature"]
        index["owners"] = []
        self.write_index(index)
        log = self.registry / "log.jsonl"
        log.unlink()
        _append_log(self.registry, _log_event("publish", "hexfmt", entry))
        self.assertIsNone(sync(self.app).lock.packages["hexfmt"]["signer"])
        (self.app / "koschei.packages.lock.json").unlink()
        self.manifest("1.0.0", "[policy]\nrequire_signed = true\n\n")
        with self.assertRaisesRegex(PackageError, "unsigned"):
            sync(self.app)
        sign_existing(self.registry, "hexfmt", "1.0.0", key=self.key_a)
        self.assertEqual(sync(self.app).lock.packages["hexfmt"]["signer"], self.signer_a)
        with self.assertRaisesRegex(PackageError, "never replaced"):
            sign_existing(self.registry, "hexfmt", "1.0.0", key=self.key_a)

    def test_keygen_writes_a_private_file_and_never_overwrites(self) -> None:
        self.assertEqual(self.key_a.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.signer_a.startswith("ed25519:"))
        with self.assertRaisesRegex(PackageError, "already exists"):
            keygen(self.key_a)
        seed, signer = load_key(self.key_a)
        self.assertEqual(signer, self.signer_a)


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
        self.assertTrue(pattern.fullmatch("/registry/log.jsonl"))
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
