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

    @unittest.skipIf(shutil.which("go") is None, "Go toolchain is unavailable")
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

            build_out = io.StringIO()
            build_err = io.StringIO()
            with redirect_stdout(build_out), redirect_stderr(build_err):
                build_code = main(["build", str(path), "-o", str(binary)])
            self.assertEqual(build_code, 0, build_err.getvalue())
            completed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, run_out.getvalue())


if __name__ == "__main__":
    unittest.main()
