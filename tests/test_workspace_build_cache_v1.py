from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from koschei.workspace import WorkspaceError, load_workspace, write_workspace_lock
from koschei.workspace_execution import build_locked_workspace_package
from koschei.workspace_package_lock import build_workspace_package_lock


def _project(root: Path, name: str, source: str) -> None:
    (root / "src").mkdir(parents=True)
    (root / "koschei.toml").write_text(
        "[package]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'entry = "src/main.ks"\n\n'
        "[capabilities]\n"
        "disk = []\n"
        "net = []\n"
        "env = []\n"
        "process = false\n",
        encoding="utf-8",
    )
    (root / "src" / "main.ks").write_text(source, encoding="utf-8")


def _workspace(root: Path) -> None:
    _project(
        root / "domain",
        "domain",
        "fn ok(value: Int) -> Bool { return value > 0 }\nfn main() {}\n",
    )
    _project(
        root / "app",
        "app",
        "import domain\n"
        'fn main() { println("cache:{domain.ok(1)}") }\n',
    )
    (root / "koschei.workspace.toml").write_text(
        'schema_version = "koschei.workspace/v1"\n\n'
        "[workspace]\n"
        'members = ["domain", "app"]\n\n'
        "[dependencies]\n"
        "domain = []\n"
        'app = ["domain"]\n',
        encoding="utf-8",
    )


def _refresh_lock(root: Path):
    lock_path = root / "koschei.workspace.lock.json"
    lock_path.unlink(missing_ok=True)
    workspace = load_workspace(root)
    write_workspace_lock(build_workspace_package_lock(workspace), lock_path)
    return workspace


@unittest.skipUnless(shutil.which("go"), "Go is required for native cache tests")
class WorkspaceBuildCacheTests(unittest.TestCase):
    def test_second_identical_build_is_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)

            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )
            second = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-b",
            )

            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertEqual(first.cache_key, second.cache_key)
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)
            self.assertEqual(first.artifact.read_bytes(), second.artifact.read_bytes())

    def test_new_locked_source_identity_gets_new_cache_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )

            domain = root / "domain" / "src" / "main.ks"
            domain.write_text(
                "fn ok(value: Int) -> Bool { return value >= 0 }\nfn main() {}\n",
                encoding="utf-8",
            )
            workspace = _refresh_lock(root)
            second = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-b",
            )

            self.assertFalse(second.cache_hit)
            self.assertNotEqual(first.cache_key, second.cache_key)

    def test_tampered_cache_artifact_blocks_hit_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )
            cached_artifact = (
                root
                / ".koschei"
                / "cache"
                / "workspace-native-v1"
                / first.cache_key
                / "artifact"
            )
            with cached_artifact.open("ab") as handle:
                handle.write(b"tamper")

            target = root / "out-b"
            with self.assertRaisesRegex(WorkspaceError, "cache artifact digest mismatch"):
                build_locked_workspace_package(
                    workspace,
                    "app",
                    output=target,
                )
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".workspace-build.json").exists())

    def test_independent_cache_misses_produce_same_native_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
                cache_dir=root / "cache-a",
            )
            second = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-b",
                cache_dir=root / "cache-b",
            )

            self.assertFalse(first.cache_hit)
            self.assertFalse(second.cache_hit)
            self.assertEqual(first.cache_key, second.cache_key)
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)
            self.assertEqual(first.artifact.read_bytes(), second.artifact.read_bytes())

    def test_incomplete_cache_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )
            entry = (
                root
                / ".koschei"
                / "cache"
                / "workspace-native-v1"
                / first.cache_key
            )
            (entry / "manifest.json").unlink()

            with self.assertRaisesRegex(WorkspaceError, "cache entry is incomplete"):
                build_locked_workspace_package(
                    workspace,
                    "app",
                    output=root / "out-b",
                )


if __name__ == "__main__":
    unittest.main()
