from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.workspace import (
    WorkspaceError,
    build_workspace_lock,
    load_workspace,
    load_workspace_lock,
    verify_workspace_lock,
    write_workspace_lock,
)
from koschei.workspace_entry import main as workspace_main


def _write_project(root: Path, name: str, source: str = "fn main() {}\n") -> None:
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


def _write_workspace(
    root: Path,
    members: list[str],
    dependencies: dict[str, list[str]],
) -> None:
    lines = [
        'schema_version = "koschei.workspace/v1"',
        "",
        "[workspace]",
        "members = [",
    ]
    lines.extend(f'  "{member}",' for member in members)
    lines.extend(["]", "", "[dependencies]"])
    for name in sorted(dependencies):
        values = ", ".join(f'"{value}"' for value in dependencies[name])
        lines.append(f"{name} = [{values}]")
    lines.append("")
    (root / "koschei.workspace.toml").write_text("\n".join(lines), encoding="utf-8")


def _commerce_workspace(root: Path, *, network_catalog: bool = False) -> None:
    _write_project(root / "libs" / "domain", "domain")
    catalog_source = "fn main() {}\n"
    if network_catalog:
        catalog_source = (
            "fn main(caps: SystemCaps) {\n"
            '    let api = caps.net.allow("https://catalog.example.com")\n'
            "}\n"
        )
    _write_project(root / "services" / "catalog", "catalog", catalog_source)
    _write_project(root / "services" / "orders", "orders")
    _write_workspace(
        root,
        ["services/orders", "libs/domain", "services/catalog"],
        {
            "catalog": ["domain"],
            "domain": [],
            "orders": ["domain", "catalog"],
        },
    )


class WorkspaceGraphTests(unittest.TestCase):
    def test_deterministic_dependency_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            workspace = load_workspace(root)
            self.assertEqual(workspace.build_order, ("domain", "catalog", "orders"))
            self.assertEqual(
                [member.name for member in workspace.members],
                ["catalog", "domain", "orders"],
            )

    def test_cycle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_project(root / "a", "alpha")
            _write_project(root / "b", "beta")
            _write_workspace(
                root,
                ["a", "b"],
                {"alpha": ["beta"], "beta": ["alpha"]},
            )
            with self.assertRaisesRegex(WorkspaceError, "cycle"):
                load_workspace(root)

    def test_unknown_dependency_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_project(root / "a", "alpha")
            _write_workspace(root, ["a"], {"alpha": ["missing"]})
            with self.assertRaisesRegex(WorkspaceError, "unknown workspace package"):
                load_workspace(root)

    def test_duplicate_package_name_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_project(root / "a", "same")
            _write_project(root / "b", "same")
            _write_workspace(root, ["a", "b"], {"same": []})
            with self.assertRaisesRegex(WorkspaceError, "duplicate workspace package names"):
                load_workspace(root)

    def test_member_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            _write_workspace(root, ["../outside"], {})
            with self.assertRaisesRegex(WorkspaceError, "unsafe workspace member path"):
                load_workspace(root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            outside = base / "outside"
            root.mkdir()
            _write_project(outside, "outside")
            try:
                os.symlink(outside, root / "linked", target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink unavailable: {error}")
            _write_workspace(root, ["linked"], {"outside": []})
            with self.assertRaisesRegex(WorkspaceError, "symlink"):
                load_workspace(root)

    def test_large_dependency_chain_has_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            members: list[str] = []
            dependencies: dict[str, list[str]] = {}
            expected: list[str] = []
            previous: str | None = None
            for index in range(128):
                name = f"pkg{index:03d}"
                relative = f"packages/{name}"
                _write_project(root / relative, name)
                members.append(relative)
                dependencies[name] = [] if previous is None else [previous]
                expected.append(name)
                previous = name
            _write_workspace(root, list(reversed(members)), dependencies)
            workspace = load_workspace(root)
            self.assertEqual(workspace.build_order, tuple(expected))


class WorkspaceLockTests(unittest.TestCase):
    def test_lock_is_deterministic_and_binds_every_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            workspace = load_workspace(root)
            first = build_workspace_lock(workspace)
            second = build_workspace_lock(load_workspace(root))
            self.assertEqual(first, second)
            self.assertEqual(
                [member.name for member in first.members],
                ["domain", "catalog", "orders"],
            )
            self.assertEqual(len(first.workspace_digest), 64)
            for member in first.members:
                self.assertEqual(len(member.manifest_sha256), 64)
                self.assertEqual(len(member.module_lock_digest), 64)

    def test_source_drift_invalidates_workspace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            workspace = load_workspace(root)
            locked = build_workspace_lock(workspace)
            source = root / "services" / "orders" / "src" / "main.ks"
            source.write_text('fn main() { println("changed") }\n', encoding="utf-8")
            with self.assertRaisesRegex(WorkspaceError, "orders"):
                verify_workspace_lock(load_workspace(root), locked)

    def test_manifest_dependency_drift_invalidates_workspace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            locked = build_workspace_lock(load_workspace(root))
            _write_workspace(
                root,
                ["services/orders", "libs/domain", "services/catalog"],
                {"catalog": ["domain"], "domain": [], "orders": ["domain"]},
            )
            with self.assertRaisesRegex(WorkspaceError, "manifest digest changed"):
                verify_workspace_lock(load_workspace(root), locked)

    def test_lock_loader_rejects_unknown_fields_and_digest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            lock = build_workspace_lock(load_workspace(root))
            path = root / "koschei.workspace.lock.json"
            write_workspace_lock(lock, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["unexpected"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(WorkspaceError, "unknown fields"):
                load_workspace_lock(path)

    def test_lock_is_no_replace_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            lock = build_workspace_lock(load_workspace(root))
            path = root / "koschei.workspace.lock.json"
            write_workspace_lock(lock, path)
            original = path.read_bytes()
            with self.assertRaisesRegex(WorkspaceError, "already exists"):
                write_workspace_lock(lock, path)
            self.assertEqual(path.read_bytes(), original)


class WorkspaceCliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = workspace_main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_check_compiles_every_member_and_reports_build_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            code, output, error = self._run(["check", str(root), "--json"])
            self.assertEqual(code, 0, error)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["member_count"], 3)
            self.assertEqual(payload["build_order"], ["domain", "catalog", "orders"])
            self.assertGreaterEqual(payload["functions"], 3)

    def test_caps_aggregates_and_workspace_deny_gate_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root, network_catalog=True)
            code, output, error = self._run(["caps", str(root), "--json"])
            self.assertEqual(code, 0, error)
            payload = json.loads(output)
            self.assertEqual(payload["domains"], ["net"])

            code, _, _ = self._run(["caps", str(root), "--deny", "net"])
            self.assertEqual(code, 2)

    def test_cli_lock_create_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _commerce_workspace(root)
            lock = root / "workspace.lock.json"
            code, output, error = self._run(
                ["lock", "create", str(root), "--output", str(lock), "--json"]
            )
            self.assertEqual(code, 0, error)
            created = json.loads(output)
            self.assertEqual(created["members"], 3)
            self.assertTrue(lock.is_file())

            code, output, error = self._run(
                ["lock", "verify", str(root), "--lock", str(lock), "--json"]
            )
            self.assertEqual(code, 0, error)
            verified = json.loads(output)
            self.assertEqual(verified["workspace_digest"], created["workspace_digest"])


if __name__ == "__main__":
    unittest.main()
