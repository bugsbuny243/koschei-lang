from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.fallible_mir_v1 import MirFallibleIsSuccess, MirFallibleUnwrap
from koschei.mir import require_mir
from koschei.mir_ir import MirAstFallback
from koschei.mir_native_runtime import (
    MirNativeProgramError,
    inspect_native_mir_support,
    run_mir_native,
)
from koschei.modules import check_graph, load_graph


class FallibleMirV1Tests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    @staticmethod
    def instructions(mir):
        return [
            instruction
            for module in mir.modules.values()
            for function in module.functions
            for block in function.blocks
            for instruction in block.instructions
        ]

    def test_or_return_lowers_to_explicit_mir_and_executes_success_edge(self) -> None:
        mir = self.checked_mir(
            """
fn risky() -> Int or Error {
    return 7
}

fn main() {
    let value = risky() or return Error("wrapped")
    println(value)
}
"""
        )
        instructions = self.instructions(mir)
        self.assertTrue(any(isinstance(item, MirFallibleIsSuccess) for item in instructions))
        self.assertTrue(any(isinstance(item, MirFallibleUnwrap) for item in instructions))
        self.assertFalse(
            any(
                isinstance(item, MirAstFallback)
                and item.node_kind == "OrReturnExpression"
                for item in instructions
            )
        )

        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), "7\n")

    def test_or_return_failure_edge_returns_replacement_error_from_main(self) -> None:
        mir = self.checked_mir(
            """
fn risky() -> Int or Error {
    return Error("inner")
}

fn main() {
    let value = risky() or return Error("wrapped")
    println(value)
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)
        with self.assertRaisesRegex(MirNativeProgramError, "wrapped"):
            run_mir_native(mir)

    def test_parallel_map_or_return_round_trips_normalized_list_shape(self) -> None:
        mir = self.checked_mir(
            """
fn square(value: Int) -> Int {
    return value * value
}

fn main() {
    let mapped = parallel_map([1, 2, 3], square, 2) or return Error("parallel failed")
    for value in mapped {
        println(value)
    }
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), "1\n4\n9\n")


if __name__ == "__main__":
    unittest.main()
