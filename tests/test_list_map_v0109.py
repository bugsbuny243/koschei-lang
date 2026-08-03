from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei import _typed_ops
from koschei.ast_nodes import SourceLocation
from koschei.cli import main
from koschei.semantic import SemanticError
from koschei.type_system import INT, NamedType, generic


class ListMapV0109Tests(unittest.TestCase):
    def run_cli(self, source: str, *arguments: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([*arguments, str(path)])
            return code, stdout.getvalue(), stderr.getvalue()

    def assert_native_parity(self, source: str, expected: str) -> None:
        if shutil.which("go") is None:
            self.skipTest("Go toolchain is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "main.ks"
            binary = root / "app"
            path.write_text(source, encoding="utf-8")

            run_out = io.StringIO()
            run_err = io.StringIO()
            with redirect_stdout(run_out), redirect_stderr(run_err):
                run_code = main(["run", str(path)])
            self.assertEqual(run_code, 0, run_err.getvalue())
            self.assertEqual(run_out.getvalue(), expected)

            build_out = io.StringIO()
            build_err = io.StringIO()
            with redirect_stdout(build_out), redirect_stderr(build_err):
                build_code = main(["build", str(path), "-o", str(binary)])
            self.assertEqual(build_code, 0, build_err.getvalue())
            completed = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, expected)

    def test_map_preserves_order_input_and_named_function_values(self):
        source = """
fn square(value: Int) -> Int {
    return value * value
}
fn length(value: String) -> Int {
    return value.length()
}
fn main() {
    let values = [1, 2, 3, 4]
    let transform = square
    println(values.map(transform))
    println(values)
    println(["a", "bbb"].map(length))
}
"""
        self.assert_native_parity(
            source,
            "[1, 4, 9, 16]\n[1, 2, 3, 4]\n[1, 3]\n",
        )

    def test_map_preserves_generic_and_nested_callback_contracts(self):
        source = """
fn identity<T>(value: T) -> T {
    return value
}
fn size(values: List<Int>) -> Int {
    return values.length()
}
fn duplicate(value: Int) -> List<Int> {
    return [value, value]
}
fn main() {
    println([1, 2, 3].map(identity))
    println([[1, 2], [], [3]].map(size))
    println([4, 5].map(duplicate))
}
"""
        self.assert_native_parity(
            source,
            "[1, 2, 3]\n[2, 0, 1]\n[[4, 4], [5, 5]]\n",
        )

    def test_map_handles_empty_typed_lists(self):
        source = """
fn square(value: Int) -> Int {
    return value * value
}
fn main() {
    let values: List<Int> = []
    println(values.map(square))
}
"""
        self.assert_native_parity(source, "[]\n")

    def test_map_rejects_non_callable_wrong_arity_and_parameter_mismatch(self):
        cases = (
            (
                """
fn square(value: Int) -> Int { return value * value }
fn main() { println([1].map()) }
""",
                "KS1301",
            ),
            (
                """
fn square(value: Int) -> Int { return value * value }
fn main() { println([1].map(square, square)) }
""",
                "KS1301",
            ),
            (
                """
fn add(left: Int, right: Int) -> Int { return left + right }
fn main() { println([1].map(add)) }
""",
                "KS1301",
            ),
            (
                """
fn length(value: String) -> Int { return value.length() }
fn main() { println([1].map(length)) }
""",
                "KS1301",
            ),
            (
                "fn main() { println([1].map(3)) }\n",
                "KS1301",
            ),
        )
        for source, expected_code in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn(expected_code, stderr)

    def test_map_rejects_raw_error_callbacks(self):
        source = """
fn fail(value: Int) -> Error {
    return Error("no")
}
fn main() {
    println([1].map(fail))
}
"""
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1306", stderr)

    def test_map_rejects_capability_callback_signatures(self):
        callback = generic("Fn", INT, NamedType("NetCaps"))
        with self.assertRaises(SemanticError) as raised:
            _typed_ops.method_type(
                generic("List", INT),
                "map",
                (callback,),
                SourceLocation(1, 1),
            )
        self.assertEqual(raised.exception.code, "KS2402")


if __name__ == "__main__":
    unittest.main()
