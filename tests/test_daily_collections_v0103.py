from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class DailyCollectionsV0103Tests(unittest.TestCase):
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

    def test_first_difference_is_structural_and_native(self):
        source = """
fn main() {
    println(["a", "b"].first_difference(["a", "B"]))
    println([1, 2].first_difference([1, 2]))
    println([1, 2].first_difference([1, 2, 3]))
}
"""
        self.assert_native_parity(source, "Some(1)\nNone\nSome(2)\n")

    def test_first_difference_preserves_option_int_contract(self):
        source = """
fn difference<T>(left: List<T>, right: List<T>) -> Option<Int> {
    return left.first_difference(right)
}
fn main() { println(difference([1, 2], [1, 3])) }
"""
        self.assert_native_parity(source, "Some(1)\n")

    def test_map_merge_overlays_immutably_with_native_parity(self):
        source = """
fn main() {
    let defaults: Map<String, Int> = {"port": 8080, "workers": 2}
    let supplied: Map<String, Int> = {"workers": 4, "debug": 1}
    let config = defaults.merge(supplied)
    println(config.get("port") or 0)
    println(config.get("workers") or 0)
    println(config.get("debug") or 0)
    println(defaults.get("workers") or 0)
}
"""
        self.assert_native_parity(source, "8080\n4\n1\n2\n")

    def test_map_merge_preserves_generic_contract(self):
        source = """
fn overlay<V>(base: Map<String, V>, supplied: Map<String, V>) -> Map<String, V> {
    return base.merge(supplied)
}
fn main() { println(overlay({"a": 1}, {"b": 2})) }
"""
        self.assert_native_parity(source, '{"a": 1, "b": 2}\n')

    def test_helpers_reject_wrong_collection_arguments(self):
        difference = 'fn main() { println([1].first_difference("x")) }\n'
        code, _, stderr = self.run_cli(difference, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)

        merge = 'fn main() { let values: Map<String, Int> = {} println(values.merge([1])) }\n'
        code, _, stderr = self.run_cli(merge, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
