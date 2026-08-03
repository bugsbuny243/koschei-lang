from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class ListFlattenV0107Tests(unittest.TestCase):
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

    def test_flatten_preserves_order_immutability_and_one_level_contract(self):
        source = """
fn main() {
    let groups: List<List<Int>> = [[1, 2], [3, 4]]
    let flat = groups.flatten()
    let empty: List<List<Int>> = []
    let deep: List<List<List<Int>>> = [[[1]], [[2, 3]]]
    println(flat)
    println(groups)
    println(empty.flatten())
    println(deep.flatten())
}
"""
        self.assert_native_parity(
            source,
            "[1, 2, 3, 4]\n[[1, 2], [3, 4]]\n[]\n[[1], [2, 3]]\n",
        )

    def test_flatten_preserves_exact_generic_contract(self):
        source = """
fn flatten_all<T>(groups: List<List<T>>) -> List<T> {
    return groups.flatten()
}
fn main() {
    println(flatten_all([["a"], ["b", "c"]]))
}
"""
        self.assert_native_parity(source, '["a", "b", "c"]\n')

    def test_flatten_rejects_non_nested_and_unproven_lists(self):
        direct = "fn main() { println([1, 2].flatten()) }\n"
        code, _, stderr = self.run_cli(direct, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1306", stderr)

        generic = """
fn invalid<T>(values: List<T>) -> List<T> {
    return values.flatten()
}
fn main() { println(1) }
"""
        code, _, stderr = self.run_cli(generic, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1306", stderr)

    def test_flatten_rejects_arguments(self):
        source = "fn main() { println([[1]].flatten(1)) }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
