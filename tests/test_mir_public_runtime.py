from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.interpreter import KoscheiRuntimeError
from koschei.mir import require_mir
from koschei.mir_scope_safety import inspect_mir_scope_safety
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import runtime_execution_mode, run_mir_with_budget


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicMirRuntimeTests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_hello_uses_native_mir_without_ast_compatibility(self) -> None:
        graph = load_graph(REPO_ROOT / "examples" / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        self.assertEqual(runtime_execution_mode(mir), "mir_native_v1")

        output = io.StringIO()
        with patch(
            "koschei.runtime_budget.BudgetedInterpreter.execute_main",
            side_effect=AssertionError("AST compatibility path must not run"),
        ), redirect_stdout(output):
            code = run_mir_with_budget(mir)

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "Koschei\n1\n")

    def test_not_yet_normalized_for_loop_uses_explicit_compatibility_mode(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    for value in [1, 2, 3] {
        println(value)
    }
}
"""
        )
        self.assertEqual(runtime_execution_mode(mir), "ast_compat_v1")
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_with_budget(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "1\n2\n3\n")

    def test_lexical_shadowing_fails_closed_to_compatibility_mode(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let x = 1
    if true {
        let x = 2
        println(x)
    }
    println(x)
}
"""
        )
        scope = inspect_mir_scope_safety(mir)
        self.assertFalse(scope.safe)
        self.assertTrue(any("shadowed binding" in reason for reason in scope.reasons))
        self.assertEqual(runtime_execution_mode(mir), "ast_compat_v1")

        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_with_budget(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "2\n1\n")

    def test_native_mir_obeys_public_step_budget(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let mut n = 0
    while true {
        n = n + 1
    }
}
"""
        )
        self.assertEqual(runtime_execution_mode(mir), "mir_native_v1")
        with self.assertRaises(KoscheiRuntimeError) as caught:
            run_mir_with_budget(mir, max_steps=8)
        self.assertEqual(caught.exception.code, "KS3601")

    def test_native_mir_obeys_public_call_depth_budget(self) -> None:
        mir = self.checked_mir(
            """
fn recurse(value: Int) -> Int {
    return recurse(value + 1)
}

fn main() {
    println(recurse(0))
}
"""
        )
        self.assertEqual(runtime_execution_mode(mir), "mir_native_v1")
        with self.assertRaises(KoscheiRuntimeError) as caught:
            run_mir_with_budget(mir, max_call_depth=4)
        self.assertEqual(caught.exception.code, "KS3602")


if __name__ == "__main__":
    unittest.main()
