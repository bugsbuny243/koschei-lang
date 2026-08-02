from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class ErgonomicsV010Tests(unittest.TestCase):
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

    def test_generic_option_return_uses_real_option_abi(self):
        source = """
fn first<T>(items: List<T>) -> Option<T> {
    return items.get(0)
}

fn main() {
    let value = first([7])
    match value {
        Some(v) => {
            println("{v}")
        }
        None => {
            println("none")
        }
    }
}
"""
        code, stdout, stderr = self.run_cli(source, "run")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "7\n")

    def test_daily_ergonomics_work_together(self):
        source = """
struct Counter { value: Int }

fn main() {
    let mut counter: Counter = Counter { value: 0 }
    for i in [1, 2, 3, 4, 5] {
        if i == 2 { continue }
        counter.value = counter.value + 1
        if i % 4 == 0 { break }
    }
    match Some(counter.value) {
        Some(v) => {
            println("count")
            println("{v}")
        }
        None => {
            println("none")
        }
    }
}
"""
        code, stdout, stderr = self.run_cli(source, "run")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "count\n3\n")

    def test_modulo_rejects_float(self):
        source = "fn main() { println(\"{5.0 % 2.0}\") }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)

    def test_negative_modulo_is_truncated_toward_zero(self):
        source = """
fn main() {
    println("{-5 % 3}")
    println("{5 % -3}")
    println("{-5 % -3}")
}
"""
        self.assert_native_parity(source, "-2\n2\n-2\n")

    def test_local_annotation_mismatch_reports_both_types(self):
        source = 'fn main() { let value: String = 5 println(value) }\n'
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)
        self.assertIn("String", stderr)
        self.assertIn("Int", stderr)

    def test_immutable_struct_field_recommends_let_mut(self):
        source = """
struct Counter { value: Int }
fn main() {
    let counter = Counter { value: 0 }
    counter.value = 1
}
"""
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS3201", stderr)
        self.assertIn("let mut", stderr)

    def test_match_block_tail_is_the_expression_value(self):
        source = """
fn main() {
    let result: Int = match Some(4) {
        Some(v) => {
            println("found")
            v + 1
        }
        None => {
            0
        }
    }
    println("{result}")
}
"""
        self.assert_native_parity(source, "found\n5\n")

    def test_break_outside_loop_is_ks1901(self):
        source = "fn main() { break }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1901", stderr)
        self.assertIn("Loop control outside a loop", stderr)

    def test_parser_error_is_localized(self):
        source = "fn main() { let value: Int 5 }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertRegex(stderr, r"KS100[1-5]")
        self.assertNotRegex(stderr, r"[çğıöşüÇĞİÖŞÜ]")

    def test_native_and_interpreter_parity(self):
        source = """
fn main() {
    for i in [1, 2, 3, 4] {
        if i == 2 { continue }
        if i % 4 == 0 { break }
        println("{i % 3}")
    }
}
"""
        self.assert_native_parity(source, "1\n0\n")

    def test_break_inside_match_targets_the_loop_not_go_switch(self):
        source = """
fn main() {
    for i in [1, 2, 3] {
        match Some(i) {
            Some(v) => {
                if v == 2 { break }
                println("{v}")
            }
            None => {}
        }
    }
}
"""
        self.assert_native_parity(source, "1\n")


if __name__ == "__main__":
    unittest.main()
