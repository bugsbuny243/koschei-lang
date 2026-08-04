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


class ListScanV0112Tests(unittest.TestCase):
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

    def test_scan_builds_running_totals_with_native_parity(self):
        source = """
fn add(total: Int, value: Int) -> Int { return total + value }
fn main() {
    let values = [5, 3, 2, 7]
    let reducer = add
    println(values.scan(0, reducer))
    println(values)
}
"""
        self.assert_native_parity(
            source,
            "[5, 8, 10, 17]\n[5, 3, 2, 7]\n",
        )

    def test_scan_handles_empty_generic_and_nested_accumulators(self):
        source = """
fn positive(total: Int, value: Int) -> Int { return total + value }
fn take_latest<T>(state: T, value: T) -> T { return value }
fn append(total: List<Int>, value: Int) -> List<Int> { return total.push(value) }
fn main() {
    let empty: List<Int> = []
    let seed: List<Int> = []
    println(empty.scan(0, positive))
    println([1, 2, 3].scan(0, take_latest))
    println([4, 5].scan(seed, append))
}
"""
        self.assert_native_parity(
            source,
            "[]\n[1, 2, 3]\n[[4], [4, 5]]\n",
        )

    def test_scan_rejects_wrong_arity_non_callable_and_bad_contracts(self):
        cases = (
            """
fn add(total: Int, value: Int) -> Int { return total + value }
fn main() { println([1].scan(0)) }
""",
            """
fn add(total: Int, value: Int) -> Int { return total + value }
fn main() { println([1].scan(0, add, add)) }
""",
            """
fn one(value: Int) -> Int { return value }
fn main() { println([1].scan(0, one)) }
""",
            """
fn wrong(total: String, value: Int) -> String { return total }
fn main() { println([1].scan(0, wrong)) }
""",
            """
fn wrong(total: Int, value: String) -> Int { return total }
fn main() { println([1].scan(0, wrong)) }
""",
            """
fn wrong(total: Int, value: Int) -> String { return "bad" }
fn main() { println([1].scan(0, wrong)) }
""",
            "fn main() { println([1].scan(0, 3)) }\n",
        )
        for source in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn("KS1301", stderr)

    def test_scan_has_exact_type_and_rejects_capabilities(self):
        callback = generic("Fn", INT, INT, INT)
        self.assertEqual(
            _typed_ops.method_type(
                generic("List", INT),
                "scan",
                (INT, callback),
                SourceLocation(1, 1),
            ),
            generic("List", INT),
        )

        capability_callback = generic(
            "Fn",
            NamedType("NetCaps"),
            INT,
            NamedType("NetCaps"),
        )
        with self.assertRaises(SemanticError) as raised:
            _typed_ops.method_type(
                generic("List", INT),
                "scan",
                (NamedType("NetCaps"), capability_callback),
                SourceLocation(1, 1),
            )
        self.assertEqual(raised.exception.code, "KS2402")


if __name__ == "__main__":
    unittest.main()
