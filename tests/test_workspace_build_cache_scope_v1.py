from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from koschei.workspace import load_workspace, write_workspace_lock
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
        'fn main() { println("app:{domain.ok(1)}") }\n',
    )
    _project(
        root / "metrics",
        "metrics",
        'fn main() { println("metrics-v1") }\n',
    )
    (root / "koschei.workspace.toml").write_text(
        'schema_version = "koschei.workspace/v1"\n\n'
        "[workspace]\n"
        'members = ["domain", "app", "metrics"]\n\n'
        "[dependencies]\n"
        "domain = []\n"
        'app = ["domain"]\n'
        "metrics = []\n",
        encoding="utf-8",
    )


def _refresh_lock(root: Path):
    path = root / "koschei.workspace.lock.json"
    path.unlink(missing_ok=True)
    workspace = load_workspace(root)
    lock = build_workspace_package_lock(workspace)
    write_workspace_lock(lock, path)
    return workspace, lock


@unittest.skipUnless(shutil.which("go"), "Go is required for native cache tests")
class WorkspaceBuildCacheScopeTests(unittest.TestCase):
    def test_unrelated_package_change_preserves_selected_package_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _workspace(root)
            workspace, first_lock = _refresh_lock(root)
            first = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "app-a",
            )
            self.assertFalse(first.cache_hit)

            (root / "metrics" / "src" / "main.ks").write_text(
                'fn main() { println("metrics-v2") }\n',
                encoding="utf-8",
            )
            workspace, second_lock = _refresh_lock(root)
            self.assertNotEqual(first_lock.workspace_digest, second_lock.workspace_digest)

            second = build_locked_workspace_package(
                workspace,
                "app",
                output=root / "app-b",
            )
            self.assertTrue(second.cache_hit)
            self.assertEqual(first.cache_key, second.cache_key)
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)
            self.assertNotEqual(first.workspace_digest, second.workspace_digest)


if __name__ == "__main__":
    unittest.main()
