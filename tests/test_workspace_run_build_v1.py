from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.workspace import WorkspaceError, load_workspace, write_workspace_lock
from koschei.workspace_execution import (
    build_locked_workspace_package,
    run_locked_workspace_package,
    verify_workspace_build,
)
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


def _commerce(root: Path) -> None:
    _project(
        root / "libs" / "domain",
        "domain",
        "fn stock_ok(stock: Int) -> Bool { return stock > 0 }\n"
        "fn main() {}\n",
    )
    _project(
        root / "services" / "catalog",
        "catalog",
        "import domain\n"
        "fn sellable(stock: Int) -> Bool { return domain.stock_ok(stock) }\n"
        "fn main() {}\n",
    )
    _project(
        root / "services" / "orders",
        "orders",
        "import catalog\n"
        "fn main() { println(\"orders:{catalog.sellable(2)}\") }\n",
    )
    (root / "koschei.workspace.toml").write_text(
        'schema_version = "koschei.workspace/v1"\n\n'
        "[workspace]\n"
        'members = ["libs/domain", "services/catalog", "services/orders"]\n\n'
        "[dependencies]\n"
        "domain = []\n"
        'catalog = ["domain"]\n'
        'orders = ["catalog"]\n',
        encoding="utf-8",
    )


def _lock(root: Path):
    workspace = load_workspace(root)
    lock = build_workspace_package_lock(workspace)
    path = root / "koschei.workspace.lock.json"
    write_workspace_lock(lock, path)
    return workspace, lock, path


class WorkspaceRunBuildTests(unittest.TestCase):
    def test_run_requires_workspace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace = load_workspace(root)
            with self.assertRaisesRegex(WorkspaceError, "requires a verified lock"):
                run_locked_workspace_package(workspace, "orders")

    def test_locked_package_runs_cross_package_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            output = io.StringIO()
            with redirect_stdout(output):
                code = run_locked_workspace_package(workspace, "orders")
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), "orders:true\n")

    def test_source_drift_blocks_run_before_program_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            domain = root / "libs" / "domain" / "src" / "main.ks"
            domain.write_text(
                "fn stock_ok(stock: Int) -> Bool { return false }\n"
                "fn main() {}\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                with self.assertRaisesRegex(WorkspaceError, "domain"):
                    run_locked_workspace_package(workspace, "orders")
            self.assertEqual(output.getvalue(), "")

    def test_unknown_package_fails_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            with self.assertRaisesRegex(WorkspaceError, "unknown workspace package"):
                run_locked_workspace_package(workspace, "missing")

    @unittest.skipUnless(shutil.which("go"), "Go is required for native parity")
    def test_native_build_matches_interpreter_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, lock, _ = _lock(root)

            interpreter = io.StringIO()
            with redirect_stdout(interpreter):
                self.assertEqual(run_locked_workspace_package(workspace, "orders"), 0)

            target = root / "out" / "orders"
            result = build_locked_workspace_package(
                workspace,
                "orders",
                output=target,
            )
            verify_workspace_build(result)
            completed = subprocess.run(
                [str(result.artifact)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, interpreter.getvalue())
            self.assertEqual(completed.stdout, "orders:true\n")
            self.assertEqual(result.workspace_digest, lock.workspace_digest)

            manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["package"], "orders")
            self.assertEqual(manifest["workspace_digest"], lock.workspace_digest)
            self.assertEqual(manifest["artifact_sha256"], result.artifact_sha256)
            self.assertEqual(manifest["mir_fingerprint"], result.mir_fingerprint)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build")
    def test_native_build_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            target = root / "orders-bin"
            build_locked_workspace_package(workspace, "orders", output=target)
            original = target.read_bytes()
            with self.assertRaisesRegex(WorkspaceError, "artifact already exists"):
                build_locked_workspace_package(workspace, "orders", output=target)
            self.assertEqual(target.read_bytes(), original)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build")
    def test_tampered_binary_fails_build_manifest_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            result = build_locked_workspace_package(
                workspace,
                "orders",
                output=root / "orders-bin",
            )
            with result.artifact.open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaisesRegex(WorkspaceError, "artifact digest mismatch"):
                verify_workspace_build(result)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build")
    def test_source_drift_blocks_build_without_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce(root)
            workspace, _, _ = _lock(root)
            catalog = root / "services" / "catalog" / "src" / "main.ks"
            catalog.write_text(
                "import domain\n"
                "fn sellable(stock: Int) -> Bool { return false }\n"
                "fn main() {}\n",
                encoding="utf-8",
            )
            target = root / "orders-bin"
            with self.assertRaisesRegex(WorkspaceError, "catalog"):
                build_locked_workspace_package(workspace, "orders", output=target)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".workspace-build.json").exists())


if __name__ == "__main__":
    unittest.main()
