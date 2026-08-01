from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import koschei  # installs the bootstrap Data ABI
from koschei.codegen_go import generate_go
from koschei.interpreter import run
from koschei.parser import parse
from koschei.semantic import SemanticError, check
from koschei.stdlib_catalog import CATALOG, document, validate_catalog

GO_BINARY = shutil.which("go")


SOURCE = r'''
fn main() {
    let value = parse_json("{\"b\":1.00,\"a\":[true,null],\"emoji\":\"\\ud83d\\ude00\"}") or return
    let encoded = encode_json(value) or return
    println(encoded)
}
'''


def compile_source(source: str) -> str:
    program = parse(source)
    check(program)
    return generate_go(program)


class DataLanguageV1Tests(unittest.TestCase):
    def test_semantic_surface_accepts_data_roundtrip(self) -> None:
        check(parse(SOURCE))

    def test_parse_and_encode_are_fallible(self) -> None:
        cases = (
            'fn main() { let value = parse_json("{}") }',
            'fn main() { let parsed = parse_json("{}") or return let value = encode_json(parsed) }',
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SemanticError) as context:
                    check(parse(source))
                self.assertEqual(context.exception.code, "KS1401")

    def test_wrong_argument_types_are_rejected(self) -> None:
        cases = (
            "fn main() { let value = parse_json(1) or return }",
            'fn main() { let value = encode_json("{}") or return }',
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SemanticError) as context:
                    check(parse(source))
                self.assertEqual(context.exception.code, "KS1301")

    def test_data_must_be_encoded_before_output(self) -> None:
        source = r'''
fn main() {
    let value = parse_json("{}") or return
    println(value)
}
'''
        with self.assertRaises(SemanticError) as context:
            check(parse(source))
        self.assertEqual(context.exception.code, "KS3608")

    def test_interpreter_emits_canonical_json(self) -> None:
        program = parse(SOURCE)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run(program, []), 0)
        self.assertEqual(output.getvalue(), '{"a":[true,null],"b":1,"emoji":"😀"}\n')

    def test_invalid_json_is_a_ks360x_error_value(self) -> None:
        source = r'''
fn main() {
    let value = parse_json("{\"x\":1,\"x\":2}") or return
}
'''
        program = parse(source)
        check(program)
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(run(program, []), 1)
        self.assertIn("KS3604", error.getvalue())

    def test_codegen_contains_standalone_data_runtime(self) -> None:
        generated = compile_source(SOURCE)
        self.assertIn("type KsData struct", generated)
        self.assertIn("func ksDataParse", generated)
        self.assertIn("func ksDataEncode", generated)
        self.assertNotIn('"encoding/json"', generated)

    def test_stdlib_contract_promotes_both_operations(self) -> None:
        validate_catalog()
        data = next(family for family in CATALOG if family.name == "data")
        statuses = {operation.name: operation.status for operation in data.operations}
        self.assertEqual(statuses["parse_json"], "supported")
        self.assertEqual(statuses["encode_json"], "supported")
        for operation in data.operations[:2]:
            self.assertEqual(
                set(operation.required_budgets), set(operation.enforced_budgets)
            )
        payload = document()
        rendered = next(item for item in payload["families"] if item["name"] == "data")
        self.assertEqual(rendered["status"], "bootstrap")


@unittest.skipUnless(GO_BINARY, "Go is required for native Data parity")
class DataLanguageNativeParityTests(unittest.TestCase):
    def test_native_output_matches_interpreter(self) -> None:
        generated = compile_source(SOURCE)
        interpreted = io.StringIO()
        with redirect_stdout(interpreted):
            self.assertEqual(run(parse(SOURCE), []), 0)

        with tempfile.TemporaryDirectory(prefix="koschei-data-v1-") as workspace:
            root = pathlib.Path(workspace)
            (root / "main.go").write_text(generated, encoding="utf-8")
            (root / "go.mod").write_text(
                "module data_v1_test\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = root / "program"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            completed = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, interpreted.getvalue())

    def test_native_and_interpreter_reject_duplicate_keys_with_same_code(self) -> None:
        source = r'''
fn main() {
    let value = parse_json("{\"x\":1,\"x\":2}") or return
}
'''
        generated = compile_source(source)
        interpreted_error = io.StringIO()
        with redirect_stderr(interpreted_error):
            self.assertEqual(run(parse(source), []), 1)

        with tempfile.TemporaryDirectory(prefix="koschei-data-v1-error-") as workspace:
            root = pathlib.Path(workspace)
            (root / "main.go").write_text(generated, encoding="utf-8")
            (root / "go.mod").write_text(
                "module data_v1_error_test\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = root / "program"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            completed = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("KS3604", interpreted_error.getvalue())
            self.assertIn("KS3604", completed.stderr)


if __name__ == "__main__":
    unittest.main()
