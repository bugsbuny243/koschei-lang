from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_ir import MirAstFallback
from koschei.mir_native_runtime import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph


REPO_ROOT = Path(__file__).resolve().parents[1]


class MirNativeRuntimeTests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_hello_executes_from_normalized_mir_blocks(self) -> None:
        graph = load_graph(REPO_ROOT / "examples" / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_native(mir)

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "Koschei\n1\n")

    def test_local_calls_and_scalar_arithmetic_execute_from_mir(self) -> None:
        mir = self.checked_mir(
            """
fn twice(value: Int) -> Int {
    return value * 2
}

fn main() {
    println(twice(21))
}
"""
        )
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_native(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "42\n")

    def test_loop_break_and_continue_follow_mir_cfg(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let mut n = 0
    while n < 5 {
        n = n + 1
        if n == 2 {
            continue
        }
        println(n)
        if n == 3 {
            break
        }
    }
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_native(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "1\n3\n")

    def test_list_for_break_and_continue_execute_from_iterator_mir(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    for value in [1, 2, 3, 4] {
        if value == 2 {
            continue
        }
        println(value)
        if value == 3 {
            break
        }
    }
}
"""
        )
        unexpected = [
            (
                block.id,
                instruction.node_kind,
                instruction.location.line,
                instruction.location.column,
            )
            for block in mir.root_module.functions[0].blocks
            for instruction in block.instructions
            if isinstance(instruction, MirAstFallback)
        ]
        self.assertEqual(unexpected, [], f"unexpected List-for fallbacks: {unexpected!r}")
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_native(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "1\n3\n")

    def test_normalized_list_renders_like_koschei_list(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    println([1, 2, 3])
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_native(mir)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "[1, 2, 3]\n")


if __name__ == "__main__":
    unittest.main()
