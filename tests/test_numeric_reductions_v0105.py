from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class NumericReductionsV0105Tests(unittest.TestCase):
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

    def test_int_reductions_are_checked_and_native(self):
        source = """
fn main() {
    let values = [4, 8, 15, 16, 23, 42]
    println(values.sum() or 0)
    println(values.min() or 0)
    println(values.max() or 0)
}
"""
        self.assert_native_parity(source, "108\n4\n42\n")

    def test_float_reductions_preserve_float_results(self):
        source = """
fn main() {
    let values: List<Float> = [1.5, -2.0, 4.25]
    println(values.sum() or 0.0)
    println(values.min() or 0.0)
    println(values.max() or 0.0)
}
"""
        self.assert_native_parity(source, "3.75\n-2.0\n4.25\n")

    def test_empty_lists_are_explicitly_fallible(self):
        source = """
fn main() {
    let values: List<Int> = []
    println(values.sum() or 99)
    println(values.min() or 98)
    println(values.max() or 97)
}
"""
        self.assert_native_parity(source, "99\n98\n97\n")

    def test_int_sum_overflow_is_an_error_value(self):
        source = """
fn main() {
    let values = [9223372036854775807, 1]
    println(values.sum() or -1)
}
"""
        self.assert_native_parity(source, "-1\n")

    def test_non_finite_float_is_rejected_at_runtime(self):
        source = """
fn main() {
    let invalid = "nan".to_float() or 0.0
    let values: List<Float> = [invalid]
    println(values.sum() or 7.0)
    println(values.min() or 8.0)
    println(values.max() or 9.0)
}
"""
        self.assert_native_parity(source, "7.0\n8.0\n9.0\n")

    def test_result_contract_is_exact_for_int_and_float(self):
        source = """
fn int_total(values: List<Int>) -> Result<Int, Error> {
    return values.sum()
}
fn float_min(values: List<Float>) -> Result<Float, Error> {
    return values.min()
}
fn main() {
    println(int_total([1, 2, 3]) or 0)
    println(float_min([2.5, 1.5]) or 0.0)
}
"""
        self.assert_native_parity(source, "6\n1.5\n")

    def test_reductions_fail_closed_for_wrong_static_types(self):
        cases = (
            'fn main() { println(["a", "b"].sum()) }\n',
            'fn main() { println([].min()) }\n',
        )
        for source in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn("KS1306", stderr)

    def test_reductions_reject_arguments(self):
        code, _, stderr = self.run_cli(
            "fn main() { println([1].max(1)) }\n", "--lang", "en", "check"
        )
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
