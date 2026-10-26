"""String.to_int has one rule in every executor.

Trimmed text, an optional sign and ASCII digits only, within signed 64 bits.
Python's int() also took "1_000", non-ASCII digits and values beyond Int.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.interpreter import ks_parse_int

CASES = {
    " 42 ": 42, "+7": 7, "-0": 0, "\t12\n": 12,
    "9223372036854775807": 9223372036854775807,
    "-9223372036854775808": -9223372036854775808,
    "1_000": None, "\u0661\u0662": None, "\uff11": None, "9223372036854775808": None,
    "": None, "+": None, "4.0": None, "0x1": None, "1 2": None,
}


class StringToIntTests(unittest.TestCase):
    def test_the_rule(self) -> None:
        for text, expected in CASES.items():
            with self.subTest(text=text):
                self.assertEqual(ks_parse_int(text), expected)

    def test_ks_run_and_the_binary_agree(self) -> None:
        items = ", ".join('"' + text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n") + '"' for text in CASES)
        source = f"fn main() {{\n    for t in [{items}] {{\n        println(t.to_int() or -1)\n    }}\n}}\n"
        expected = "".join(f"{-1 if value is None else value}\n" for value in CASES.values())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
            self.assertEqual(stdout.getvalue(), expected)
            if shutil.which("go") is None:
                return
            binary = Path(directory) / "app"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
            completed = subprocess.run([str(binary)], capture_output=True, timeout=60, check=True)
            self.assertEqual(completed.stdout.decode("utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
