from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class StableUniqueV0106Tests(unittest.TestCase):
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

    def test_unique_preserves_first_occurrence_and_input(self):
        source = """
fn main() {
    let values = [3, 1, 3, 2, 1]
    let result = values.unique()
    println(values)
    println(result)
}
"""
        self.assert_native_parity(source, "[3, 1, 3, 2, 1]\n[3, 1, 2]\n")

    def test_unique_uses_structural_equality_for_nested_lists(self):
        source = """
fn main() {
    let values: List<List<Int>> = [[1, 2], [1, 2], [2], [1, 2]]
    println(values.unique())
}
"""
        self.assert_native_parity(source, "[[1, 2], [2]]\n")

    def test_unique_preserves_generic_contract(self):
        source = """
fn stable<T>(values: List<T>) -> List<T> {
    return values.unique()
}
fn main() {
    println(stable(["a", "b", "a"]))
}
"""
        self.assert_native_parity(source, '["a", "b"]\n')

    def test_unique_accepts_empty_typed_list(self):
        source = """
fn main() {
    let values: List<String> = []
    println(values.unique())
}
"""
        self.assert_native_parity(source, "[]\n")

    def test_unique_rejects_arguments(self):
        source = "fn main() { println([1, 2].unique(1)) }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
