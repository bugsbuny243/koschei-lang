from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from koschei.workspace import WorkspaceError, load_workspace, write_workspace_lock
from koschei.workspace_analysis_cache import WorkspaceAnalysisIdentity
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
        'fn main() { println("analysis:{domain.ok(1)}") }\n',
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


class WorkspaceAnalysisIdentityTests(unittest.TestCase):
    def test_compiler_contract_changes_cache_key(self) -> None:
        base = WorkspaceAnalysisIdentity(
            package="app",
            member_manifest_sha256="1" * 64,
            module_lock_digest="2" * 64,
            compiler_contract_digest="3" * 64,
        )
        changed = WorkspaceAnalysisIdentity(
            package="app",
            member_manifest_sha256="1" * 64,
            module_lock_digest="2" * 64,
            compiler_contract_digest="4" * 64,
        )
        self.assertNotEqual(base.cache_key, changed.cache_key)


@unittest.skipUnless(shutil.which("go"), "Go is required for workspace build tests")
class WorkspaceAnalysisCacheTests(unittest.TestCase):
    def test_second_build_reuses_analysis_without_selected_reanalysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )
            self.assertFalse(first.analysis_cache_hit)

            with patch(
                "koschei.workspace_execution._analyze_workspace_package",
                side_effect=AssertionError("selected package was re-analysed"),
            ):
                second = build_locked_workspace_package(
                    workspace,
                    "app",
                    output=root / "out-b",
                )

            self.assertTrue(second.analysis_cache_hit)
            self.assertEqual(first.analysis_cache_key, second.analysis_cache_key)
            self.assertTrue(second.cache_hit)
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)

    def test_selected_source_change_and_new_lock_gets_new_analysis_key(self) -> None:
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

            self.assertFalse(second.analysis_cache_hit)
            self.assertNotEqual(first.analysis_cache_key, second.analysis_cache_key)

    def test_tampered_analysis_backend_fails_before_output_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "out-a",
            )
            backend = (
                root
                / ".koschei"
                / "cache"
                / "workspace-analysis-v1"
                / first.analysis_cache_key
                / "main.go"
            )
            with backend.open("a", encoding="utf-8") as handle:
                handle.write("// tamper\n")

            target = root / "out-b"
            with self.assertRaisesRegex(
                WorkspaceError,
                "analysis cache backend digest mismatch",
            ):
                build_locked_workspace_package(
                    workspace,
                    "app",
                    output=target,
                )
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".workspace-build.json").exists())

    def test_incomplete_analysis_entry_fails_closed(self) -> None:
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
                / "workspace-analysis-v1"
                / first.analysis_cache_key
            )
            (entry / "manifest.json").unlink()

            with self.assertRaisesRegex(
                WorkspaceError,
                "analysis cache entry is incomplete",
            ):
                build_locked_workspace_package(
                    workspace,
                    "app",
                    output=root / "out-b",
                )

    def test_analysis_cache_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace = _refresh_lock(root)
            real_cache = root / "real-analysis-cache"
            real_cache.mkdir()
            linked_cache = root / "linked-analysis-cache"
            try:
                linked_cache.symlink_to(real_cache, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")

            with self.assertRaisesRegex(
                WorkspaceError,
                "analysis cache root cannot be a symlink",
            ):
                build_locked_workspace_package(
                    workspace,
                    "app",
                    output=root / "out",
                    analysis_cache_dir=linked_cache,
                )


if __name__ == "__main__":
    unittest.main()
