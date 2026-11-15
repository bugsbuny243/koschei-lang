"""The `math` Core Library module: every result, every overflow, run and native agree."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

GO = shutil.which("go")

SOURCE = """
import math

fn main() {
    let lowest = -9223372036854775807 - 1
    println(math.min(3, -2))
    println(math.max(3, -2))
    println(math.clamp(15, 0, 10) or -1)
    println(math.clamp(-4, 0, 10) or -1)
    println(math.clamp(7, 0, 10) or -1)
    println(math.clamp(5, 10, 0))
    println(math.sign(-8))
    println(math.sign(0))
    println(math.sign(lowest))
    println(math.abs(-42) or -1)
    println(math.abs(-9223372036854775807) or -1)
    println(math.abs(lowest))
    println(math.is_even(10))
    println(math.is_even(-3))
    println(math.pow(2, 10) or -1)
    println(math.pow(-3, 3) or -1)
    println(math.pow(0, 0) or -1)
    println(math.pow(-2, 63) or -1)
    println(math.pow(3, 39) or -1)
    println(math.pow(1, 9223372036854775807) or -1)
    println(math.pow(-1, 9223372036854775807) or 0)
    println(math.pow(3, 40))
    println(math.pow(2, 63))
    println(math.pow(2, -1))
    println(math.gcd(48, -18) or -1)
    println(math.gcd(0, 7) or -1)
    println(math.gcd(0, 0) or -1)
    println(math.gcd(lowest, 2))
    println(math.min_float(2.5, 1.5))
    println(math.max_float(2.5, 1.5))
    println(math.abs_float(-0.5))
    println(math.clamp_float(1.5, 0.0, 1.0) or -1.0)
    println(math.clamp_float(0.5, 1.0, 0.0))
}
"""

EXPECTED = "\n".join([
    "-2", "3", "10", "0", "7",
    "math.clamp: low is greater than high",
    "-1", "0", "-1",
    "42", "9223372036854775807",
    "math.abs: the smallest Int has no absolute value within Int",
    "true", "false",
    "1024", "-27", "1", "-9223372036854775808", "4052555153018976267", "1", "-1",
    "math.pow: the result is outside Int",
    "math.pow: the result is outside Int",
    "math.pow: the exponent must not be negative",
    "6", "7", "0",
    "math.gcd: the smallest Int is out of range",
    "1.5", "2.5", "0.5", "1.0",
    "math.clamp_float: low is greater than high",
]) + "\n"


class CoreLibraryMathTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-math-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "main.ks"
        self.path.write_text(SOURCE, encoding="utf-8")

    def test_ks_run(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(self.path)]), 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), EXPECTED)

    @unittest.skipIf(GO is None, "Go is not installed")
    def test_native_binary_prints_the_same(self) -> None:
        binary = self.path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(self.path), "-o", str(binary)]), 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, EXPECTED)


if __name__ == "__main__":
    unittest.main()
