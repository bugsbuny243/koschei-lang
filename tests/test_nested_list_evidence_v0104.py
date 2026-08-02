from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main
from koschei.parser import parse
from koschei.typed_hir import lower_typed_hir
from koschei.type_system import render_type


class NestedListEvidenceV0104Tests(unittest.TestCase):
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

    def test_nested_parameter_loops_preserve_inner_type_and_native_parity(self):
        source = """
fn flatten(groups: List<List<Int>>) -> List<Int> {
    let mut flat: List<Int> = []
    for group in groups {
        for value in group {
            flat = flat.push(value)
        }
    }
    return flat
}

fn main() {
    println(flatten([[1, 2], [3], [4, 5]]))
}
"""
        self.assert_native_parity(source, "[1, 2, 3, 4, 5]\n")

    def test_three_nested_levels_keep_structural_evidence(self):
        source = """
fn main() {
    let cubes: List<List<List<Int>>> = [[[1], [2, 3]], [[4]]]
    let mut flat: List<Int> = []
    for plane in cubes {
        for row in plane {
            for value in row {
                flat = flat.push(value)
            }
        }
    }
    println(flat)
}
"""
        self.assert_native_parity(source, "[1, 2, 3, 4]\n")

    def test_direct_nested_literal_uses_typed_hir_evidence(self):
        source = """
fn main() {
    let mut total = 0
    for group in [[1, 2], [3]] {
        for value in group {
            total = total + value
        }
    }
    println(total)
}
"""
        self.assert_native_parity(source, "6\n")

    def test_typed_hir_records_exact_loop_binding_types(self):
        program = parse(
            """
fn main() {
    let groups: List<List<Int>> = [[1], [2]]
    for group in groups {
        for value in group {
            println(value)
        }
    }
}
"""
        )
        report = lower_typed_hir(program)
        self.assertIn("List<Int>", {render_type(item) for item in report.binding_types("group")})
        self.assertIn("Int", {render_type(item) for item in report.binding_types("value")})

    def test_non_list_iteration_still_fails_closed(self):
        source = "fn main() { for value in 7 { println(value) } }\n"
        code, _, stderr = self.run_cli(source, "--lang", "en", "check")
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stderr)


if __name__ == "__main__":
    unittest.main()
