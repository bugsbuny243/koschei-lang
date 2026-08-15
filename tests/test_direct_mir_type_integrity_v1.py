from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_native_runtime import (
    MirNativeProgramError,
    MirNativeRuntimeError,
    _MirExecutor,
    inspect_native_mir_support,
    run_mir_native,
)
from koschei.modules import check_graph, load_graph


INT_MAX = 9223372036854775807


class DirectMirTypeIntegrityV1Tests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_int_overflow_cannot_escape_declared_int_return_boundary(self) -> None:
        mir = self.checked_mir(
            f"""
fn overflow() -> Int {{
    return {INT_MAX} + 1
}}

fn main() {{
    println(overflow())
}}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        with self.assertRaisesRegex(MirNativeRuntimeError, "KS3106"):
            run_mir_native(mir)

    def test_overflow_can_propagate_only_when_error_is_declared_and_handled(self) -> None:
        mir = self.checked_mir(
            f"""
fn risky() -> Int or Error {{
    return {INT_MAX} + 1
}}

fn main() {{
    let value = risky() or return Error("caught overflow")
    println(value)
}}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        with self.assertRaisesRegex(MirNativeProgramError, "caught overflow"):
            run_mir_native(mir)

    def test_runtime_parameter_guard_rejects_invalid_host_value(self) -> None:
        mir = self.checked_mir(
            """
fn echo(value: Int) -> Int {
    return value
}

fn main() {
    println(echo(1))
}
"""
        )
        function = next(
            item for item in mir.root_module.functions if item.name == "echo"
        )
        executor = _MirExecutor(mir, max_steps=1000, max_call_depth=32)

        with self.assertRaisesRegex(MirNativeRuntimeError, "KS3106"):
            executor._call(function, ["bad"], mir.root)

    def test_valid_int64_path_still_executes(self) -> None:
        mir = self.checked_mir(
            """
fn add(left: Int, right: Int) -> Int {
    return left + right
}

fn main() {
    println(add(20, 22))
}
"""
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), "42\n")


if __name__ == "__main__":
    unittest.main()
