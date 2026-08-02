from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main


class CollectionRankingV0101Tests(unittest.TestCase):
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

    def test_take_is_total_immutable_and_native(self):
        source = """
fn main() {
    let values: List<Int> = [1, 2, 3, 4]
    println(values.take(2))
    println(values)
    println(values.take(99))
    println(values.take(0))
    println(values.take(-3))
}
"""
        self.assert_native_parity(
            source,
            '[1, 2]\n[1, 2, 3, 4]\n[1, 2, 3, 4]\n[]\n[]\n',
        )

    def test_map_keys_sort_by_value_is_deterministic_and_native(self):
        source = """
fn main() {
    let scores: Map<String, Int> = {"b": 2, "a": 2, "c": 3}
    println(scores.keys_sorted_by_value(true))
    println(scores.keys_sorted_by_value(false))
    println(scores.keys_sorted_by_value(true).take(2))
}
"""
        self.assert_native_parity(
            source,
            '["c", "a", "b"]\n["a", "b", "c"]\n["c", "a"]\n',
        )

    def test_ranked_keys_keep_string_item_type_through_for(self):
        source = """
fn main() {
    let scores: Map<String, Int> = {"ada": 3, "lin": 2}
    for name in scores.keys_sorted_by_value(true).take(1) {
        println(name.trim())
    }
}
"""
        code, stdout, stderr = self.run_cli(source, "run")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "ada\n")

    def test_map_sort_rejects_non_comparable_value_contract(self):
        source = """
fn main() {
    let grouped: Map<String, List<Int>> = {"a": [1, 2]}
    println(grouped.keys_sorted_by_value(true))
}
"""
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1306", stderr)

    def test_collection_method_arguments_are_checked(self):
        take = 'fn main() { println([1, 2].take("2")) }\n'
        code, _, stderr = self.run_cli(take, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)

        ranking = (
            'fn main() { let values: Map<String, Int> = {"a": 1} '
            'println(values.keys_sorted_by_value(1)) }\n'
        )
        code, _, stderr = self.run_cli(ranking, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
