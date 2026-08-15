from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.cli import main as cli_main
from koschei.codegen_go import RUNTIME_PRELUDE, generate_go_mir
from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError
from koschei.structured_tasks import (
    TASK_CANCELLED,
    StructuredTaskError,
    TaskScopeValue,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "large_service" / "task_cancellation.ks"
EXPECTED = "true\nfalse\n1\n0\n20\n-1\n1\n"
GO_BINARY = shutil.which("go")


class TaskCancellationCoreTests(unittest.TestCase):
    def test_cancel_is_stable_terminal_state_without_slot_reuse(self) -> None:
        scope = TaskScopeValue(2)
        first = scope.spawn(object(), 10)
        second = scope.spawn(object(), 20)
        self.assertEqual((first, second), (0, 1))
        self.assertTrue(scope.cancel(first))
        self.assertFalse(scope.cancel(first))
        self.assertEqual(scope.record(first).state, TASK_CANCELLED)
        self.assertEqual(scope.pending, 1)
        with self.assertRaisesRegex(StructuredTaskError, "KS3912"):
            scope.spawn(object(), 30)

    def test_cancel_all_only_counts_pending_tasks(self) -> None:
        scope = TaskScopeValue(3)
        zero = scope.spawn(object(), 0)
        scope.spawn(object(), 1)
        scope.spawn(object(), 2)
        self.assertTrue(scope.cancel(zero))
        self.assertEqual(scope.cancel_all(), 2)
        self.assertEqual(scope.cancel_all(), 0)
        self.assertEqual(scope.pending, 0)

    def test_invalid_task_id_and_closed_scope_fail_closed(self) -> None:
        scope = TaskScopeValue(1)
        scope.spawn(object(), 1)
        for task_id in (-1, 1, True):
            with self.subTest(task_id=task_id):
                with self.assertRaisesRegex(StructuredTaskError, "KS3916"):
                    scope.cancel(task_id)
        scope.closed = True
        with self.assertRaisesRegex(StructuredTaskError, "KS3913"):
            scope.cancel(0)
        with self.assertRaisesRegex(StructuredTaskError, "KS3913"):
            scope.cancel_all()

    def test_go_runtime_has_explicit_cancel_state_and_join_skip(self) -> None:
        self.assertIn("ksTaskStateCancelled", RUNTIME_PRELUDE)
        self.assertIn("func ksTaskCancel(", RUNTIME_PRELUDE)
        self.assertIn("func ksTaskCancelAll(", RUNTIME_PRELUDE)
        self.assertIn("if slot.State == ksTaskStateCancelled", RUNTIME_PRELUDE)
        self.assertIn("func ksTaskArgumentShareSafe(", RUNTIME_PRELUDE)

    def test_new_diagnostics_are_explainable(self) -> None:
        for code in ("KS3916", "KS3917"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "en"))
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))


class TaskSendSafetyLanguageTests(unittest.TestCase):
    @staticmethod
    def _graph(source: str):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return temporary, load_graph(path)

    def test_scalar_argument_is_share_safe(self) -> None:
        temporary, graph = self._graph(
            """
fn worker(value: Int) {}

fn main() {
    let scope = task_scope(1) or return
    task_spawn(scope, worker, 7) or return
    task_join_all(scope) or return
}
"""
        )
        with temporary:
            check_graph(graph)

    def test_bounded_queue_of_scalar_is_share_safe(self) -> None:
        temporary, graph = self._graph(
            """
fn worker(queue: BoundedQueue<Int>) {
    queue_try_send(queue, 7)
}

fn main() {
    let queue = bounded_queue(1, 0) or return
    let scope = task_scope(1) or return
    task_spawn(scope, worker, queue) or return
    task_join_all(scope) or return
}
"""
        )
        with temporary:
            check_graph(graph)

    def test_list_alias_cannot_cross_task_boundary(self) -> None:
        temporary, graph = self._graph(
            """
fn worker(values: List<Int>) {}

fn main() {
    let values = [1, 2]
    let scope = task_scope(1) or return
    task_spawn(scope, worker, values) or return
}
"""
        )
        with temporary:
            with self.assertRaisesRegex(SemanticError, "KS3917"):
                check_graph(graph)

    def test_map_alias_cannot_cross_task_boundary(self) -> None:
        temporary, graph = self._graph(
            """
fn worker(values: Map<String, Int>) {}

fn main() {
    let values = {"a": 1}
    let scope = task_scope(1) or return
    task_spawn(scope, worker, values) or return
}
"""
        )
        with temporary:
            with self.assertRaisesRegex(SemanticError, "KS3917"):
                check_graph(graph)

    def test_queue_of_mutable_items_is_not_future_parallel_safe(self) -> None:
        temporary, graph = self._graph(
            """
fn worker(queue: BoundedQueue<List<Int>>) {}

fn main() {
    let queue = bounded_queue(1, [0]) or return
    let scope = task_scope(1) or return
    task_spawn(scope, worker, queue) or return
}
"""
        )
        with temporary:
            with self.assertRaisesRegex(SemanticError, "KS3917"):
                check_graph(graph)


class TaskCancellationParityTests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"task cancellation interpreter exit: {code}")
        return output.getvalue()

    def test_cancelled_worker_never_runs_and_remaining_worker_keeps_order(self) -> None:
        self.assertEqual(self.interpreter_output(), EXPECTED)
        self.assertEqual(self.interpreter_output(), EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_native_cancellation_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))
        self.assertIn("ksTaskStateCancelled", generated)
        self.assertIn("func ksTaskCancel(", generated)
        self.assertIn("if slot.State == ksTaskStateCancelled", generated)

        with tempfile.TemporaryDirectory(prefix="koschei-task-cancel-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheitaskcancel\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "task-cancel-v1"
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
