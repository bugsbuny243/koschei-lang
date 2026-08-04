from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei import _typed_ops
from koschei.ast_nodes import SourceLocation
from koschei.cli import main
from koschei.semantic import SemanticError
from koschei.type_system import FLOAT, INT, STRING, NamedType, UnknownType, generic


class MapAddV0113Tests(unittest.TestCase):
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

    def test_record_aggregation_preserves_source_and_native_parity(self):
        source = """
struct Purchase {
    customer: String,
    amount: Int,
}
fn main() {
    let purchases = [
        Purchase { customer: "Ada", amount: 5 },
        Purchase { customer: "Grace", amount: 7 },
        Purchase { customer: "Ada", amount: 3 },
    ]
    let empty: Map<String, Int> = {}
    let mut totals = empty
    for purchase in purchases {
        totals = totals.add(purchase.customer, purchase.amount)
    }
    println(totals.get("Ada") or 0)
    println(totals.get("Grace") or 0)
    println(empty)
}
"""
        self.assert_native_parity(source, "8\n7\n{}\n")

    def test_add_handles_float_existing_missing_and_order(self):
        source = """
fn main() {
    let base: Map<String, Float> = {"tax": 1.5}
    let updated = base.add("tax", 0.25).add("fee", 2.0)
    println(updated)
    println(base)
}
"""
        self.assert_native_parity(
            source,
            '{"tax": 1.75, "fee": 2.0}\n{"tax": 1.5}\n',
        )

    def test_add_rejects_wrong_arity_and_static_types(self):
        cases = (
            ("fn main() { let m: Map<String, Int> = {}; println(m.add()) }\n", "KS1301"),
            ("fn main() { let m: Map<String, Int> = {}; println(m.add(\"x\")) }\n", "KS1301"),
            ("fn main() { let m: Map<String, Int> = {}; println(m.add(\"x\", 1, 2)) }\n", "KS1301"),
            ("fn main() { let m: Map<String, Int> = {}; println(m.add(1, 2)) }\n", "KS1301"),
            ("fn main() { let m: Map<String, Int> = {}; println(m.add(\"x\", \"2\")) }\n", "KS1301"),
            ("fn main() { let m: Map<String, String> = {}; println(m.add(\"x\", \"v\")) }\n", "KS1306"),
            ("fn main() { let m: Map<String, Int> = {}; println(m.add(\"x\", 1.5)) }\n", "KS1301"),
        )
        for source, code_name in cases:
            with self.subTest(source=source):
                code, _, stderr = self.run_cli(source, "--lang", "en", "check")
                self.assertEqual(code, 1)
                self.assertIn(code_name, stderr)

    def test_add_preserves_exact_type_and_security_classification(self):
        location = SourceLocation(1, 1)
        int_map = generic("Map", STRING, INT)
        float_map = generic("Map", STRING, FLOAT)
        self.assertEqual(
            _typed_ops.method_type(int_map, "add", (STRING, INT), location),
            int_map,
        )
        self.assertEqual(
            _typed_ops.method_type(float_map, "add", (STRING, FLOAT), location),
            float_map,
        )
        inferred = _typed_ops.method_type(
            generic("Map", STRING, UnknownType()),
            "add",
            (STRING, INT),
            location,
        )
        self.assertEqual(inferred, int_map)

        with self.assertRaises(SemanticError) as raised:
            _typed_ops.method_type(
                generic("Map", STRING, NamedType("NetCaps")),
                "add",
                (STRING, NamedType("NetCaps")),
                location,
            )
        self.assertEqual(raised.exception.code, "KS2402")

    def test_int_overflow_fails_with_same_code_in_both_runtimes(self):
        if shutil.which("go") is None:
            self.skipTest("Go toolchain is unavailable")
        source = """
fn main() {
    let values: Map<String, Int> = {"max": 9223372036854775807}
    println(values.add("max", 1))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "main.ks"
            binary = root / "app"
            path.write_text(source, encoding="utf-8")

            run_code, _, run_err = self.run_cli(source, "run")
            self.assertEqual(run_code, 1)
            self.assertIn("KS3501", run_err)

            build_out = io.StringIO()
            build_err = io.StringIO()
            with redirect_stdout(build_out), redirect_stderr(build_err):
                build_code = main(["build", str(path), "-o", str(binary)])
            self.assertEqual(build_code, 0, build_err.getvalue())
            completed = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("KS3501", completed.stderr)


if __name__ == "__main__":
    unittest.main()
