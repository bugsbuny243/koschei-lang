"""Decimal multiplication, division and rescaling (financial_decimal).

Every operation names its result scale and rounding mode and rounds once, in
integers. The results are checked against an independent Fraction oracle and
must give the same bytes in every `ks run` executor and in native binaries,
which used to refuse every Decimal program.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
import io
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli
from koschei.diagnostics import lookup
from koschei.financial_decimal import (
    DIVISION_BY_ZERO_MESSAGE,
    INT64_MAX,
    INT64_MIN,
    ROUNDING_MESSAGE,
    ROUNDING_MODES,
    DecimalValue,
    FinancialDecimalError,
    decimal_text,
    div_decimal,
    mul_decimal,
    parse_decimal,
    rescale_decimal,
)
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

PROGRAM = r'''struct Line {
    sku: String
    price: Decimal
    qty: Int
}

fn line_total(line: Line) -> Decimal or Error {
    let qty = decimal("{line.qty}", 0) or return
    return decimal_mul(line.price, qty, 2, "half_even")
}

fn invoice(lines: List<Line>) -> Decimal or Error {
    let mut sum = decimal("0", 2) or return
    for line in lines {
        let total = line_total(line) or return
        sum = decimal_add(sum, total) or return
    }
    return sum
}

fn main() {
    let p1 = decimal("19.99", 2) or return
    let p2 = decimal("0.05", 2) or return
    let a = Line { sku: "k-1", price: p1, qty: 3 }
    let b = Line { sku: "k-2", price: p2, qty: 7 }
    let net = invoice([a, b]) or return
    println("net {net}")
    let rate = decimal("0.18", 2) or return
    let tax = decimal_mul(net, rate, 2, "half_up") or return
    let gross = decimal_add(net, tax) or net
    println("tax {tax} gross {gross}")
    println([net, tax])
    let again = decimal("60.32", 2) or return
    println(decimal_cmp(net, again))
    let wider = decimal("60.320", 3) or return
    println(decimal_cmp(net, wider))
    println(decimal_add(net, wider))
    for text in ["0", "-0", "-0.00", "01", "1.", ".5", "+1", " 1", "1e2", "1.234", "9223372036854775807", "-9223372036854775808", "9223372036854775808", "-92233720368547758.08", "٣"] {
        println(text)
        println(decimal(text, 2))
    }
    println(decimal("1", 19))
    println(decimal("1", -1))
    let one = decimal("1", 0) or return
    let seven = decimal("7", 0) or return
    let minus = decimal("-7", 0) or return
    for mode in ["down", "up", "floor", "ceiling", "half_up", "half_down", "half_even", "HALF_UP", ""] {
        println(mode)
        println(decimal_div(one, seven, 3, mode))
        println(decimal_div(one, minus, 3, mode))
        println(decimal_div(minus, minus, 18, mode))
    }
    for text in ["2.5", "3.5", "-2.5", "-3.5", "2.49", "-2.51", "0.5", "-0.5"] {
        let value = decimal(text, 2) or return
        println(text)
        for mode in ["half_even", "half_up", "half_down", "floor", "ceiling", "up", "down"] {
            println(decimal_rescale(value, 0, mode))
        }
    }
    let max = decimal("9223372036854775807", 0) or return
    let min = decimal("-9223372036854775808", 0) or return
    let tiny = decimal("0.000000000000000001", 18) or return
    println(decimal_add(max, one))
    println(decimal_sub(min, one))
    println(decimal_rescale(max, 1, "down"))
    println(decimal_div(max, tiny, 0, "down"))
    println(decimal_div(min, minus, 0, "down"))
    println(decimal_mul(min, one, 0, "down"))
    println(decimal_mul(tiny, tiny, 18, "up"))
    println(decimal_mul(tiny, tiny, 18, "down"))
    println(decimal_mul(tiny, tiny, 18, "foo"))
    println(decimal_mul(tiny, tiny, 40, "foo"))
    let zero = decimal("0.0", 1) or return
    println(decimal_div(one, zero, 40, "down"))
    println(decimal_div(one, zero, 2, "foo"))
    println(decimal_div(one, zero, 2, "up"))
    let minus_one = decimal("-1", 0) or return
    println(decimal_div(min, minus_one, 0, "down"))
    println(a)
    println(decimal_text(tiny))
}
'''

EXPECTED = '''net 60.32
tax 10.86 gross 71.18
[60.32, 10.86]
0
KS3802: decimal scales differ; implicit rescaling is forbidden
KS3802: decimal scales differ; implicit rescaling is forbidden
0
0.00
-0
0.00
-0.00
0.00
01
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
1.
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
.5
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
+1
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
 1
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
1e2
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
1.234
KS3801: decimal input has more fractional digits than the declared scale; implicit rounding is forbidden
9223372036854775807
KS3803: decimal atoms overflow signed int64
-9223372036854775808
KS3803: decimal atoms overflow signed int64
9223372036854775808
KS3803: decimal atoms overflow signed int64
-92233720368547758.08
-92233720368547758.08
٣
KS3801: invalid decimal text; exponent, whitespace, plus sign and non-canonical leading zeroes are forbidden
KS3801: decimal scale must be 0..18
KS3801: decimal scale must be 0..18
down
0.142
-0.142
1.000000000000000000
up
0.143
-0.143
1.000000000000000000
floor
0.142
-0.143
1.000000000000000000
ceiling
0.143
-0.142
1.000000000000000000
half_up
0.143
-0.143
1.000000000000000000
half_down
0.143
-0.143
1.000000000000000000
half_even
0.143
-0.143
1.000000000000000000
HALF_UP
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even

KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
2.5
2
3
2
2
3
3
2
3.5
4
4
3
3
4
4
3
-2.5
-2
-3
-2
-3
-2
-3
-2
-3.5
-4
-4
-3
-4
-3
-4
-3
2.49
2
2
2
2
3
3
2
-2.51
-3
-3
-3
-3
-2
-3
-2
0.5
0
1
0
0
1
1
0
-0.5
0
-1
0
-1
0
-1
0
KS3803: decimal addition overflow
KS3803: decimal subtraction overflow
KS3803: decimal rescale overflow
KS3803: decimal division overflow
1317624576693539401
-9223372036854775808
0.000000000000000001
0.000000000000000000
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3801: decimal scale must be 0..18
KS3801: decimal scale must be 0..18
KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, half_down or half_even
KS3807: decimal division by zero
KS3803: decimal division overflow
Line { sku: "k-1", price: 19.99, qty: 3 }
0.000000000000000001
'''


def _exact(value: Fraction, scale: int, mode: str) -> int:
    """The rounding rules written over exact rationals, apart from the core."""

    scaled = value * 10**scale
    low, high = math.floor(scaled), math.ceil(scaled)
    if low == high:
        return low
    toward_zero, away = (low, high) if scaled > 0 else (high, low)
    if mode == "down":
        return toward_zero
    if mode == "up":
        return away
    if mode == "floor":
        return low
    if mode == "ceiling":
        return high
    half = scaled - low
    if half != Fraction(1, 2):
        return high if half > Fraction(1, 2) else low
    if mode == "half_up":
        return away
    if mode == "half_down":
        return toward_zero
    return low if low % 2 == 0 else high


def _atoms(rng: random.Random) -> int:
    kind = rng.randrange(5)
    if kind == 0:
        return rng.randint(-1000, 1000)
    if kind == 1:
        return rng.choice((INT64_MIN, INT64_MAX, INT64_MIN + 1, INT64_MAX - 1, 0, 1, -1))
    if kind == 2:
        return rng.randint(INT64_MIN, INT64_MAX)
    return rng.randint(-(10 ** rng.randrange(1, 12)), 10 ** rng.randrange(1, 12))


def _value(rng: random.Random) -> DecimalValue:
    return DecimalValue(_atoms(rng), rng.randrange(19))


def _fraction(value: DecimalValue) -> Fraction:
    return Fraction(value.atoms, 10**value.scale)


def _expected(exact: Fraction, scale: int, mode: str, operation: str) -> object:
    atoms = _exact(exact, scale, mode)
    if not INT64_MIN <= atoms <= INT64_MAX:
        return f"KS3803: decimal {operation} overflow"
    return DecimalValue(atoms, scale)


def _outcome(call) -> object:
    try:
        return call()
    except FinancialDecimalError as error:
        return str(error)


def _cases(seed: int, count: int):
    """(name, arguments, expected) for random multiplications, divisions and rescales."""

    rng = random.Random(seed)
    for _ in range(count):
        left, right = _value(rng), _value(rng)
        scale, mode = rng.randrange(19), rng.choice(ROUNDING_MODES)
        yield "decimal_mul", (left, right, scale, mode), _expected(
            _fraction(left) * _fraction(right), scale, mode, "multiplication"
        )
        if right.atoms:
            quotient = _expected(_fraction(left) / _fraction(right), scale, mode, "division")
        else:
            quotient = DIVISION_BY_ZERO_MESSAGE
        yield "decimal_div", (left, right, scale, mode), quotient
        yield "decimal_rescale", (left, scale, mode), _expected(_fraction(left), scale, mode, "rescale")


_OPERATIONS = {"decimal_mul": mul_decimal, "decimal_div": div_decimal, "decimal_rescale": rescale_decimal}


def _write(directory: str, source: str) -> Path:
    path = Path(directory) / "main.ks"
    path.write_text(source, encoding="utf-8")
    return path


class DecimalRoundingCoreTests(unittest.TestCase):
    def test_every_mode_rounds_like_exact_rationals(self) -> None:
        for name, arguments, expected in _cases(seed=3807, count=4000):
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(_outcome(lambda: _OPERATIONS[name](*arguments)), expected)

    def test_ties_and_signs(self) -> None:
        rows = {
            "2.5": (2, 3, 2, 2, 3, 3, 2),
            "3.5": (4, 4, 3, 3, 4, 4, 3),
            "-2.5": (-2, -3, -2, -3, -2, -3, -2),
            "-0.5": (0, -1, 0, -1, 0, -1, 0),
            "2.49": (2, 2, 2, 2, 3, 3, 2),
        }
        modes = ("half_even", "half_up", "half_down", "floor", "ceiling", "up", "down")
        for text, atoms in rows.items():
            value = parse_decimal(text, 2)
            for mode, expected in zip(modes, atoms):
                with self.subTest(text=text, mode=mode):
                    self.assertEqual(rescale_decimal(value, 0, mode), DecimalValue(expected, 0))

    def test_the_contract_is_checked_scale_mode_then_divisor(self) -> None:
        one, zero = parse_decimal("1", 0), parse_decimal("0.0", 1)
        for call, message in (
            (lambda: div_decimal(one, zero, 19, "nearest"), "KS3801: decimal scale must be 0..18"),
            (lambda: div_decimal(one, zero, 2, "nearest"), ROUNDING_MESSAGE),
            (lambda: div_decimal(one, zero, 2, "up"), DIVISION_BY_ZERO_MESSAGE),
            (lambda: mul_decimal(one, one, -1, "up"), "KS3801: decimal scale must be 0..18"),
            (lambda: rescale_decimal(one, 2, "HALF_UP"), ROUNDING_MESSAGE),
        ):
            with self.subTest(message=message):
                self.assertEqual(_outcome(call), message)

    def test_long_text_is_an_overflow_not_a_host_conversion_limit(self) -> None:
        for text in ("1" * 8193, "-" + "9" * 5000 + ".5", "0." + "0" * 17 + "1"):
            with self.subTest(length=len(text)):
                outcome = _outcome(lambda: parse_decimal(text, 18))
                if text.startswith("0."):
                    self.assertEqual(outcome, DecimalValue(1, 18))
                else:
                    self.assertEqual(outcome, "KS3803: decimal atoms overflow signed int64")
        self.assertEqual(parse_decimal("-92233720368547758.08", 2), DecimalValue(INT64_MIN, 2))


class DecimalLanguageTests(unittest.TestCase):
    def check(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, source)
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(cli(["check", str(path)]), 1, output.getvalue())
            return output.getvalue()

    def test_the_checker_types_the_new_operations(self) -> None:
        head = 'fn main() {\n    let a = decimal("1.00", 2) or return\n'
        for line in (
            "    println(decimal_mul(a, a))\n",
            '    println(decimal_mul(a, a, "2", "up"))\n',
            "    println(decimal_div(a, a, 2, 1))\n",
            '    println(decimal_rescale(a, "up"))\n',
            '    println(decimal_rescale(1, 2, "up"))\n',
        ):
            with self.subTest(line=line.strip()):
                self.assertIn("KS1301", self.check(head + line + "}\n"))
        output = self.check(head + "    println(a == a)\n}\n")
        self.assertIn("KS3804", output)

    def test_division_by_zero_is_explained(self) -> None:
        for language in ("en", "tr"):
            with self.subTest(language=language):
                self.assertIsNotNone(lookup("KS3807", language))
        self.assertIn("decimal_mul()", lookup("KS3804", "en").fix)


class DecimalExecutorTests(unittest.TestCase):
    def outputs(self, source: str) -> dict[str, str]:
        results: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, source)
            graph = load_graph(path)
            check_graph(graph)
            mir = graph.mir
            root = mir.root_module
            runs = {
                "ks run": lambda: cli(["run", str(path)]),
                "canonical": lambda: _run_budgeted_canonical_mir(mir, [], runtime_budget.RuntimeBudget()),
                "ast": lambda: runtime_budget.BudgetedInterpreter(
                    root.program,
                    [],
                    namespaces=mir.namespaces(),
                    imports=dict(root.imports),
                    enums=mir.enums(),
                    module_imports=mir.module_imports(),
                    structs=mir.structs(),
                    budget=runtime_budget.RuntimeBudget(),
                ).execute_main(),
                "direct": lambda: run_mir_native(mir),
            }
            self.assertTrue(inspect_native_mir_support(mir).supported)
            for name, run in runs.items():
                stdout = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                    with runtime_budget.host_recursion_headroom():
                        run()
                results[name] = stdout.getvalue()
        return results

    def test_every_ks_run_executor_computes_the_same(self) -> None:
        for name, output in self.outputs(PROGRAM).items():
            with self.subTest(executor=name):
                self.assertEqual(output, EXPECTED)

    def test_struct_fields_hold_decimal_and_data_in_every_executor(self) -> None:
        source = (
            "struct Box {\n    data: Data\n    amount: Decimal\n}\n\n"
            'fn main() {\n    let data = parse_json("[1]") or return\n'
            '    let amount = decimal("1.50", 2) or return\n'
            "    let box = Box { data: data, amount: amount }\n"
            "    println(box.amount)\n    println(encode_json(box.data))\n}\n"
        )
        for name, output in self.outputs(source).items():
            with self.subTest(executor=name):
                self.assertEqual(output, "1.50\n[1]\n")

    @unittest.skipUnless(GO, "Go is not installed")
    def test_binaries_compute_like_ks_run(self) -> None:
        # The fixed program, then random operands at every scale and near both
        # int64 bounds, each compared with the Python core.
        lines = []
        expected = []
        for name, arguments, outcome in _cases(seed=1807, count=150):
            texts = []
            for argument in arguments:
                if isinstance(argument, DecimalValue):
                    texts.append(f'"{decimal_text(argument)}", {argument.scale}')
                elif isinstance(argument, int):
                    texts.append(str(argument))
                else:
                    texts.append(f'"{argument}"')
            helper = "rescale" if name == "decimal_rescale" else name[len("decimal_"):]
            lines.append(f"    println({helper}({', '.join(texts)}))\n")
            expected.append(decimal_text(outcome) if isinstance(outcome, DecimalValue) else outcome)
        fuzz = (
            "fn mul(a: String, sa: Int, b: String, sb: Int, scale: Int, mode: String) -> Decimal or Error {\n"
            "    let x = decimal(a, sa) or return\n    let y = decimal(b, sb) or return\n"
            "    return decimal_mul(x, y, scale, mode)\n}\n\n"
            "fn div(a: String, sa: Int, b: String, sb: Int, scale: Int, mode: String) -> Decimal or Error {\n"
            "    let x = decimal(a, sa) or return\n    let y = decimal(b, sb) or return\n"
            "    return decimal_div(x, y, scale, mode)\n}\n\n"
            "fn rescale(a: String, sa: Int, scale: Int, mode: String) -> Decimal or Error {\n"
            "    let x = decimal(a, sa) or return\n    return decimal_rescale(x, scale, mode)\n}\n\n"
            "fn main() {\n" + "".join(lines) + "}\n"
        )
        cases = ((PROGRAM, EXPECTED), (fuzz, "".join(f"{item}\n" for item in expected)))
        for source, stdout in cases:
            with tempfile.TemporaryDirectory() as directory:
                _write(directory, source)
                build = subprocess.run(
                    [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"],
                    cwd=directory, env=dict(os.environ, PYTHONPATH=str(ROOT)),
                    capture_output=True, timeout=300, check=False,
                )
                self.assertEqual(build.returncode, 0, build.stderr.decode())
                native = subprocess.run(
                    [str(Path(directory) / "app")], capture_output=True, timeout=60, check=False,
                )
                ran = subprocess.run(
                    [sys.executable, "-m", "koschei", "run", "main.ks"],
                    cwd=directory, env=dict(os.environ, PYTHONPATH=str(ROOT)),
                    capture_output=True, timeout=300, check=False,
                )
                self.assertEqual((native.returncode, native.stderr.decode()), (0, ""))
                self.assertEqual(native.stdout.decode(), stdout)
                self.assertEqual(ran.stdout.decode(), stdout)


if __name__ == "__main__":
    unittest.main()
