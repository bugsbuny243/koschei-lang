from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from koschei.workspace import WorkspaceError, load_workspace, write_workspace_lock
from koschei.workspace_package_lock import (
    build_workspace_package_lock,
    verify_workspace_package_lock,
)


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
        'fn main() { println("index:{domain.ok(1)}") }\n',
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


def _lock(root: Path):
    workspace = load_workspace(root)
    locked = build_workspace_package_lock(workspace)
    write_workspace_lock(locked, root / "koschei.workspace.lock.json")
    return workspace, locked


def _index_entry(root: Path, digest: str) -> Path:
    return (
        root
        / ".koschei"
        / "cache"
        / "workspace-lock-index-v1"
        / digest
    )


class WorkspaceLockIndexTests(unittest.TestCase):
    def test_second_verify_does_not_enter_full_graph_semantic_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)

            first = verify_workspace_package_lock(workspace, locked)
            self.assertEqual(first.workspace_digest, locked.workspace_digest)
            self.assertTrue((_index_entry(root, locked.workspace_digest) / "manifest.json").is_file())

            with patch(
                "koschei.workspace_lock_index.verify_workspace_package_lock_full",
                side_effect=AssertionError("full parser/semantic verifier was invoked"),
            ):
                second = verify_workspace_package_lock(workspace, locked)
            self.assertEqual(second.workspace_digest, locked.workspace_digest)

    def test_source_digest_change_is_rejected_on_index_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            verify_workspace_package_lock(workspace, locked)

            source = root / "domain" / "src" / "main.ks"
            source.write_text(
                "fn ok(value: Int) -> Bool { return false }\nfn main() {}\n",
                encoding="utf-8",
            )
            with patch(
                "koschei.workspace_lock_index.verify_workspace_package_lock_full",
                side_effect=AssertionError("stale index must not fall back silently"),
            ):
                with self.assertRaisesRegex(WorkspaceError, "source digest changed"):
                    verify_workspace_package_lock(workspace, locked)

    def test_added_unused_source_is_conservatively_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            verify_workspace_package_lock(workspace, locked)

            (root / "app" / "src" / "unused.ks").write_text(
                "fn unused() -> Int { return 1 }\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkspaceError, "source set changed"):
                verify_workspace_package_lock(workspace, locked)

    def test_project_manifest_change_is_rejected_without_full_source_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            verify_workspace_package_lock(workspace, locked)

            manifest = root / "app" / "koschei.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    'version = "0.1.0"',
                    'version = "0.1.1"',
                ),
                encoding="utf-8",
            )
            changed_workspace = load_workspace(root)
            with patch(
                "koschei.workspace_lock_index.verify_workspace_package_lock_full",
                side_effect=AssertionError("metadata drift should fail before full parse"),
            ):
                with self.assertRaisesRegex(WorkspaceError, "member identity changed: app"):
                    verify_workspace_package_lock(changed_workspace, locked)

    def test_refreshed_lock_uses_new_digest_scoped_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            verify_workspace_package_lock(workspace, locked)
            old_entry = _index_entry(root, locked.workspace_digest)

            source = root / "domain" / "src" / "main.ks"
            source.write_text(
                "fn ok(value: Int) -> Bool { return value >= 0 }\nfn main() {}\n",
                encoding="utf-8",
            )
            changed_workspace = load_workspace(root)
            refreshed = build_workspace_package_lock(changed_workspace)
            self.assertNotEqual(refreshed.workspace_digest, locked.workspace_digest)

            verified = verify_workspace_package_lock(changed_workspace, refreshed)
            self.assertEqual(verified.workspace_digest, refreshed.workspace_digest)
            self.assertTrue(old_entry.is_dir())
            self.assertTrue(_index_entry(root, refreshed.workspace_digest).is_dir())

    def test_tampered_current_index_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            verify_workspace_package_lock(workspace, locked)

            manifest = _index_entry(root, locked.workspace_digest) / "manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["sources"][0]["sha256"] = "0" * 64
            manifest.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkspaceError, "index digest mismatch"):
                verify_workspace_package_lock(workspace, locked)

    def test_symlinked_cache_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, locked = _lock(root)
            real = root / "real-cache"
            real.mkdir()
            link = root / ".koschei"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")

            with self.assertRaisesRegex(WorkspaceError, "symlink component"):
                verify_workspace_package_lock(workspace, locked)


if __name__ == "__main__":
    unittest.main()
