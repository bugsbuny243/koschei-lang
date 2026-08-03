from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class ListChunksV0108Tests(unittest.TestCase):
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

    def test_chunks_preserve_order_tail_and_input(self):
        source = """
fn main() {
    let values = [1, 2, 3, 4, 5, 6, 7]
    let batches = values.chunks(3) or []
    println(batches)
    println(values)
}
"""
        self.assert_native_parity(
            source,
            "[[1, 2, 3], [4, 5, 6], [7]]\n[1, 2, 3, 4, 5, 6, 7]\n",
        )

    def test_chunks_preserve_generic_and_nested_generic_contracts(self):
        source = """
fn chunk<T>(values: List<T>, size: Int) -> Result<List<List<T>>, Error> {
    return values.chunks(size)
}
fn main() {
    println(chunk(["a", "b", "c"], 2) or [])
    let nested: List<List<Int>> = [[1], [2], [3]]
    let grouped: List<List<List<Int>>> = nested.chunks(2) or []
    println(grouped)
}
"""
        self.assert_native_parity(
            source,
            '[["a", "b"], ["c"]]\n[[[1], [2]], [[3]]]\n',
        )

    def test_chunks_handle_empty_and_oversized_groups(self):
        source = """
fn main() {
    let empty: List<Int> = []
    println(empty.chunks(3) or [[9]])
    println([1, 2].chunks(10) or [])
}
"""
        self.assert_native_parity(source, "[]\n[[1, 2]]\n")

    def test_chunks_reject_non_positive_sizes_explicitly(self):
        source = """
fn main() {
    println([1, 2].chunks(0) or [[9]])
    println([1, 2].chunks(-1) or [[8]])
}
"""
        self.assert_native_parity(source, "[[9]]\n[[8]]\n")

    def test_chunks_reject_wrong_arity_and_size_type(self):
        cases = (
            'fn main() { println([1].chunks()) }\n',
            'fn main() { println([1].chunks(1, 2)) }\n',
            'fn main() { println([1].chunks("2")) }\n',
        )
        for source in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
