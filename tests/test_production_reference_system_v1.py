from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.capabilities import analyze_graph
from koschei.modules import check_graph
from koschei.workspace import load_workspace, write_workspace_lock
from koschei.workspace_execution import (
    build_locked_workspace_package,
    run_locked_workspace_package,
    verify_workspace_build,
)
from koschei.workspace_modules import load_workspace_member_graph
from koschei.workspace_package_lock import build_workspace_package_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "examples" / "production_reference_v1"
EXPECTED_OUTPUT = (
    "trade quantity=25 price=10100 notional=252500 buyer_cash=-252626 seller_cash=252450 fees=176 balanced=true\n"
    "trade quantity=0 price=10100 notional=0 buyer_cash=0 seller_cash=0 fees=0 balanced=true\n"
    "trade quantity=0 price=10100 notional=0 buyer_cash=0 seller_cash=0 fees=0 balanced=true\n"
)


def _copy_reference() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name) / "production_reference_v1"
    shutil.copytree(REFERENCE, root)
    return temporary, root


def _lock(root: Path):
    workspace = load_workspace(root)
    lock = build_workspace_package_lock(workspace)
    lock_path = root / "koschei.workspace.lock.json"
    write_workspace_lock(lock, lock_path)
    return workspace, lock


def _project(root: Path, name: str, source: str) -> None:
    root.mkdir(parents=True)
    (root / "koschei.toml").write_text(
        "[package]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'entry = "matter.ks"\n\n'
        "[capabilities]\n"
        "disk = []\n"
        "net = []\n"
        "env = []\n"
        "process = false\n",
        encoding="utf-8",
    )
    (root / "matter.ks").write_text(source, encoding="utf-8")


def _scale_workspace(root: Path, count: int = 32) -> None:
    members: list[str] = []
    dependencies: dict[str, list[str]] = {}
    for index in range(count):
        name = f"scale{index:02d}"
        member = f"realms/{name}"
        members.append(member)
        if index == 0:
            source = "fn value() -> Int { return 1 }\nfn main() {}\n"
            dependencies[name] = []
        else:
            previous = f"scale{index - 1:02d}"
            source = (
                f"import {previous}\n"
                f"fn value() -> Int {{ return {previous}.value() + 1 }}\n"
                + ("fn main() { println(value()) }\n" if index == count - 1 else "fn main() {}\n")
            )
            dependencies[name] = [previous]
        _project(root / member, name, source)

    lines = [
        'schema_version = "koschei.workspace/v1"',
        "",
        "[workspace]",
        "members = [",
        *(f'  "{member}",' for member in members),
        "]",
        "",
        "[dependencies]",
    ]
    for index in range(count):
        name = f"scale{index:02d}"
        deps = ", ".join(f'"{dep}"' for dep in dependencies[name])
        lines.append(f"{name} = [{deps}]")
    lines.append("")
    (root / "koschei.workspace.toml").write_text("\n".join(lines), encoding="utf-8")


class ProductionReferenceSystemTests(unittest.TestCase):
    def test_committed_reference_is_real_multi_realm_program(self) -> None:
        workspace = load_workspace(REFERENCE)
        self.assertEqual(len(workspace.members), 10)

        module_count = 0
        function_count = 0
        domains_by_member: dict[str, list[str]] = {}
        for name in workspace.build_order:
            graph = load_workspace_member_graph(workspace, name)
            report = check_graph(graph)
            module_count += len(graph.modules)
            function_count += report.functions
            domains_by_member[name] = analyze_graph(graph).domains()

        self.assertGreaterEqual(module_count, 10)
        self.assertGreaterEqual(function_count, 25)
        self.assertEqual(domains_by_member["order_worker"], [])
        self.assertEqual(domains_by_member["matching_engine"], [])
        self.assertEqual(domains_by_member["risk_engine"], [])
        self.assertEqual(domains_by_member["ledger_engine"], [])
        self.assertEqual(domains_by_member["market_feed"], ["net"])

    def test_reference_runs_through_verified_workspace_lock(self) -> None:
        temporary, root = _copy_reference()
        self.addCleanup(temporary.cleanup)
        workspace, _ = _lock(root)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_locked_workspace_package(workspace, "order_worker"), 0)
        self.assertEqual(output.getvalue(), EXPECTED_OUTPUT)

    def test_reference_source_drift_fails_closed_before_execution(self) -> None:
        temporary, root = _copy_reference()
        self.addCleanup(temporary.cleanup)
        workspace, _ = _lock(root)
        target = root / "realms" / "risk_engine" / "matter.ks"
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "return quantity_lots <= max_quantity_lots",
                "return true",
            ),
            encoding="utf-8",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            with self.assertRaisesRegex(Exception, "risk_engine"):
                run_locked_workspace_package(workspace, "order_worker")
        self.assertEqual(output.getvalue(), "")

    @unittest.skipUnless(shutil.which("go"), "Go is required for production native parity")
    def test_reference_native_binary_matches_interpreter(self) -> None:
        temporary, root = _copy_reference()
        self.addCleanup(temporary.cleanup)
        workspace, lock = _lock(root)

        interpreter = io.StringIO()
        with redirect_stdout(interpreter):
            self.assertEqual(run_locked_workspace_package(workspace, "order_worker"), 0)

        result = build_locked_workspace_package(
            workspace,
            "order_worker",
            output=root / "order-worker",
        )
        verify_workspace_build(result)
        completed = subprocess.run(
            [str(result.artifact)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(interpreter.getvalue(), EXPECTED_OUTPUT)
        self.assertEqual(completed.stdout, EXPECTED_OUTPUT)
        self.assertEqual(result.workspace_digest, lock.workspace_digest)

    def test_workspace_scale_gate_32_realm_transitive_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _scale_workspace(root, 32)
            workspace, _ = _lock(root)
            graph = load_workspace_member_graph(workspace, "scale31")
            report = check_graph(graph)

            self.assertEqual(len(workspace.members), 32)
            self.assertEqual(len(graph.modules), 32)
            self.assertGreaterEqual(report.functions, 64)

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(run_locked_workspace_package(workspace, "scale31"), 0)
            self.assertEqual(output.getvalue(), "32\n")

    @unittest.skipUnless(shutil.which("go"), "Go is required for scale native build")
    def test_workspace_scale_gate_32_realm_native_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _scale_workspace(root, 32)
            workspace, _ = _lock(root)
            result = build_locked_workspace_package(
                workspace,
                "scale31",
                output=root / "scale31-bin",
            )
            verify_workspace_build(result)
            completed = subprocess.run(
                [str(result.artifact)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "32\n")


if __name__ == "__main__":
    unittest.main()
