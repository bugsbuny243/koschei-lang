from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go
from koschei.financial_decimal import (
    DecimalValue,
    FinancialDecimalError,
    INT64_MAX,
    add_decimal,
    compare_decimal,
    decimal_text,
    parse_decimal,
    sub_decimal,
)
from koschei.financial_decimal_v1 import _GO_RUNTIME
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "financial_exchange" / "decimal_v1.ks"
EXPECTED = "101.2500\n101.3750\n-1\n101.2500\n"
GO_BINARY = shutil.which("go")


class FinancialDecimalCoreTests(unittest.TestCase):
    def test_parse_preserves_explicit_scale_without_float(self) -> None:
        value = parse_decimal("101.2500", 4)
        self.assertEqual(value, DecimalValue(1_012_500, 4))
        self.assertEqual(decimal_text(value), "101.2500")
        self.assertEqual(parse_decimal("-0.0000", 4), DecimalValue(0, 4))

    def test_noncanonical_or_lossy_input_fails_closed(self) -> None:
        for raw, scale in (
            ("01.00", 2),
            ("+1.00", 2),
            (" 1.00", 2),
            ("1e2", 2),
            ("1.234", 2),
        ):
            with self.subTest(raw=raw, scale=scale):
                with self.assertRaises(FinancialDecimalError):
                    parse_decimal(raw, scale)

    def test_scale_mismatch_never_rescales_implicitly(self) -> None:
        left = parse_decimal("1.00", 2)
        right = parse_decimal("1.000", 3)
        for operation in (add_decimal, sub_decimal, compare_decimal):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(FinancialDecimalError, "KS3802"):
                    operation(left, right)

    def test_checked_addition_and_subtraction_reject_int64_overflow(self) -> None:
        maximum = DecimalValue(INT64_MAX, 0)
        one = DecimalValue(1, 0)
        with self.assertRaisesRegex(FinancialDecimalError, "KS3803"):
            add_decimal(maximum, one)
        minimum = DecimalValue(-(2**63), 0)
        with self.assertRaisesRegex(FinancialDecimalError, "KS3803"):
            sub_decimal(minimum, one)

    def test_compare_is_exact_for_equal_scale(self) -> None:
        low = parse_decimal("99.9900", 4)
        same = parse_decimal("99.9900", 4)
        high = parse_decimal("100.0000", 4)
        self.assertEqual(compare_decimal(low, high), -1)
        self.assertEqual(compare_decimal(low, same), 0)
        self.assertEqual(compare_decimal(high, low), 1)

    def test_decimal_native_runtime_contains_no_float_parser(self) -> None:
        self.assertNotIn("ParseFloat", _GO_RUNTIME)
        self.assertNotIn("float64", _GO_RUNTIME)


class FinancialDecimalLanguageTests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"Decimal example interpreter exit: {code}")
        return output.getvalue()

    def test_decimal_crosses_function_type_boundary(self) -> None:
        source = """
fn render(value: Decimal) -> String {
    return decimal_text(value)
}

fn main() {
    let value = decimal("12.340", 3) or return
    println(render(value))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)

    def test_float_cannot_enter_decimal_constructor(self) -> None:
        source = """
fn main() {
    let value = decimal(1.25, 2) or return
    println(decimal_text(value))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "String"):
                check_graph(graph)

    def test_public_runtime_is_exact_and_deterministic(self) -> None:
        first = self.interpreter_output()
        second = self.interpreter_output()
        self.assertEqual(first, EXPECTED)
        self.assertEqual(second, EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_native_decimal_output_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go(graph.root_module.program, graph)
        self.assertIn("type KsDecimal struct", generated)

        with tempfile.TemporaryDirectory(prefix="koschei-decimal-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheidecimal\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "decimal-v1"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            executed = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(executed.stdout, EXPECTED)
            self.assertEqual(executed.stdout, self.interpreter_output())


if __name__ == "__main__":
    unittest.main()
