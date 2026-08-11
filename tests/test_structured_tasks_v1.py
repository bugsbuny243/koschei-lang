from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go_mir
from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError
from koschei.structured_tasks import StructuredTaskError, TaskScopeValue
from koschei.structured_tasks_v1 import _GO_RUNTIME


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "large_service" / "structured_tasks.ks"
EXPECTED = "0\n0\n1\n2\nfalse\n0\ntrue\n10\n20\n"
GO_BINARY = shutil.which("go")


class StructuredTaskCoreTests(unittest.TestCase):
    def test_capacity_is_hard_bounded_and_storage_does_not_grow(self) -> None:
        for capacity in (0, -1, 4097):
            with self.subTest(capacity=capacity):
                with self.assertRaisesRegex(StructuredTaskError, "KS3911"):
                    TaskScopeValue(capacity)
        with self.assertRaisesRegex(StructuredTaskError, "KS3911"):
            TaskScopeValue(True)

        scope = TaskScopeValue(2)
        self.assertEqual(len(scope._slots), 2)
        self.assertEqual(scope.spawn(object(), 10), 0)
        self.assertEqual(scope.spawn(object(), 20), 1)
        self.assertEqual(len(scope._slots), 2)
        with self.assertRaisesRegex(StructuredTaskError, "KS3912"):
            scope.spawn(object(), 30)
        self.assertEqual(len(scope._slots), 2)

    def test_closed_scope_rejects_new_work(self) -> None:
        scope = TaskScopeValue(1)
        scope.closed = True
        with self.assertRaisesRegex(StructuredTaskError, "KS3913"):
            scope.spawn(object(), 1)

    def test_go_runtime_uses_fixed_task_slots(self) -> None:
        self.assertIn("make([]ksTaskSlot, int(capacity))", _GO_RUNTIME)
        self.assertNotIn("append(scope.Slots", _GO_RUNTIME)
        self.assertIn("scope.Closed = true", _GO_RUNTIME)
        self.assertIn("for index := int64(0); index < scope.Count; index++", _GO_RUNTIME)

    def test_task_diagnostics_are_explainable(self) -> None:
        for code in ("KS3911", "KS3912", "KS3913", "KS3914", "KS3915"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "en"))
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))


class StructuredTaskLanguageTests(unittest.TestCase):
    @staticmethod
    def _check(source: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"structured task interpreter exit: {code}")
        return output.getvalue()

    def test_worker_argument_type_is_checked_structurally(self) -> None:
        source = """
fn worker(value: Int) {}

fn main() {
    let scope = task_scope(1) or return
    task_spawn(scope, worker, "wrong") or return
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS1301"):
                check_graph(graph)

    def test_worker_must_be_unary(self) -> None:
        source = """
fn worker() {}

fn main() {
    let scope = task_scope(1) or return
    task_spawn(scope, worker, 1) or return
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS3914"):
                check_graph(graph)

    def test_worker_return_value_cannot_be_silently_discarded(self) -> None:
        source = """
fn worker(value: Int) -> Int { return value }

fn main() {
    let scope = task_scope(1) or return
    task_spawn(scope, worker, 1) or return
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS3914"):
                check_graph(graph)

    def test_capability_worker_argument_is_rejected(self) -> None:
        source = """
fn worker(net: NetCaps) {}

fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let scope = task_scope(1) or return
    task_spawn(scope, worker, net) or return
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS3914"):
                check_graph(graph)

    def test_function_value_alias_is_not_a_spawn_escape_hatch(self) -> None:
        source = """
fn worker(value: Int) {}

fn main() {
    let alias = worker
    let scope = task_scope(1) or return
    task_spawn(scope, alias, 1) or return
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS3914"):
                check_graph(graph)

    def test_public_runtime_is_deterministic_and_spawn_ordered(self) -> None:
        self.assertEqual(self.interpreter_output(), EXPECTED)
        self.assertEqual(self.interpreter_output(), EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_public_native_build_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))
        self.assertIn("type KsTaskScope struct", generated)
        self.assertIn("scope.Closed = true", generated)
        self.assertIn("make([]ksTaskSlot, int(capacity))", generated)

        with tempfile.TemporaryDirectory(prefix="koschei-tasks-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheitasks\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "tasks-v1"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            executed = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(executed.stdout, EXPECTED)
            self.assertEqual(executed.stdout, self.interpreter_output())


if __name__ == "__main__":
    unittest.main()
