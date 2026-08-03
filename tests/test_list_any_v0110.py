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
from koschei.type_system import BOOL, INT, NamedType, generic


class ListAnyV0110Tests(unittest.TestCase):
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

    def test_any_short_circuits_and_preserves_source(self):
        source = """
fn stop_before_failure(value: Int) -> Bool {
    if value == 1 { return true }
    return 1 / 0 > 0
}
fn main() {
    let values = [1, 2, 3]
    let predicate = stop_before_failure
    println(values.any(predicate))
    println(values)
}
"""
        self.assert_native_parity(source, "true\n[1, 2, 3]\n")

    def test_any_handles_empty_false_generic_and_nested_inputs(self):
        source = """
fn identity<T>(value: T) -> T { return value }
fn above_ten(value: Int) -> Bool { return value > 10 }
fn non_empty(values: List<Int>) -> Bool { return values.length() > 0 }
fn main() {
    let empty: List<Int> = []
    println(empty.any(above_ten))
    println([1, 2, 3].any(above_ten))
    println([false, true].any(identity))
    println([[], [4]].any(non_empty))
}
"""
        self.assert_native_parity(source, "false\nfalse\ntrue\ntrue\n")

    def test_any_rejects_non_callable_wrong_arity_and_bad_contracts(self):
        cases = (
            """
fn yes(value: Int) -> Bool { return true }
fn main() { println([1].any()) }
""",
            """
fn yes(value: Int) -> Bool { return true }
fn main() { println([1].any(yes, yes)) }
""",
            """
fn both(left: Int, right: Int) -> Bool { return true }
fn main() { println([1].any(both)) }
""",
            """
fn non_empty(value: String) -> Bool { return value.length() > 0 }
fn main() { println([1].any(non_empty)) }
""",
            """
fn number(value: Int) -> Int { return value }
fn main() { println([1].any(number)) }
""",
            "fn main() { println([1].any(3)) }\n",
        )
        for source in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn("KS1301", stderr)

    def test_any_rejects_capability_callback_signatures(self):
        callback = generic("Fn", INT, BOOL)
        self.assertEqual(
            _typed_ops.method_type(
                generic("List", INT),
                "any",
                (callback,),
                SourceLocation(1, 1),
            ),
            BOOL,
        )
        capability_callback = generic("Fn", NamedType("NetCaps"), BOOL)
        with self.assertRaises(SemanticError) as raised:
            _typed_ops.method_type(
                generic("List", NamedType("NetCaps")),
                "any",
                (capability_callback,),
                SourceLocation(1, 1),
            )
        self.assertEqual(raised.exception.code, "KS2402")


if __name__ == "__main__":
    unittest.main()
