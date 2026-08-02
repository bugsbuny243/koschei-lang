from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class ListFindV0102Tests(unittest.TestCase):
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

    def test_find_returns_first_match_and_none_with_native_parity(self):
        source = """
fn is_even(value: Int) -> Bool { return value % 2 == 0 }
fn is_large(value: Int) -> Bool { return value > 20 }

fn main() {
    println([1, 3, 6, 8].find(is_even))
    println([1, 3, 6, 8].find(is_large))
}
"""
        self.assert_native_parity(source, "Some(6)\nNone\n")

    def test_find_preserves_generic_option_contract(self):
        source = """
fn is_even(value: Int) -> Bool { return value % 2 == 0 }
fn first_even(values: List<Int>) -> Option<Int> { return values.find(is_even) }

fn main() {
    match first_even([1, 4, 6]) {
        Some(value) => println("{value}"),
        None => println("none"),
    }
}
"""
        self.assert_native_parity(source, "4\n")

    def test_find_requires_named_single_argument_bool_predicate(self):
        literal = "fn main() { println([1, 2].find(true)) }\n"
        code, _, stderr = self.run_cli(literal, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)

        wrong_arity = """
fn invalid(left: Int, right: Int) -> Bool { return left == right }
fn main() { println([1, 2].find(invalid)) }
"""
        code, _, stderr = self.run_cli(wrong_arity, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)

        wrong_return = """
fn invalid(value: Int) -> Int { return value }
fn main() { println([1, 2].find(invalid)) }
"""
        code, _, stderr = self.run_cli(wrong_return, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
