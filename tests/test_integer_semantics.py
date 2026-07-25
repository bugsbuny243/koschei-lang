from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei.codegen_go import generate_go
from koschei.interpreter import Interpreter, KsError
from koschei.parser import parse
from koschei.semantic import INT_MAX, INT_MIN, SemanticError, check

GO_BINARY = shutil.which("go")
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class Int64SemanticTests(unittest.TestCase):
    def compile(self, source: str):
        program = parse(source)
        check(program)
        return program

    def test_signed_64_bit_boundaries_are_accepted(self) -> None:
        self.compile(
            f"fn main() {{ let hi = {INT_MAX} let lo = {INT_MIN} }}"
        )

    def test_positive_literal_above_max_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1302"):
            self.compile(f"fn main() {{ let x = {INT_MAX + 1} }}")

    def test_negative_literal_below_min_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS1302"):
            self.compile(f"fn main() {{ let x = {INT_MIN - 1} }}")

    def test_runtime_rejects_out_of_range_literal_without_semantic_check(self) -> None:
        program = parse(f"fn main() {{ return {INT_MAX + 1} }}")
        result = Interpreter(program, []).execute_main()
        self.assertIsInstance(result, KsError)
        self.assertIn("KS3501", result.message)

    def test_interpreter_overflows_are_error_values(self) -> None:
        cases = (
            f"{INT_MAX} + 1",
            f"{INT_MIN} - 1",
            f"{INT_MAX} * 2",
            f"-({INT_MIN})",
        )
        for expression in cases:
            with self.subTest(expression=expression):
                program = self.compile(
                    f'fn main() {{ return {expression} or Error("overflow") }}'
                )
                result = Interpreter(program, []).execute_main()
                self.assertIsInstance(result, KsError)
                self.assertEqual(result.message, "overflow")


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native parite testi atlandı")
class Int64NativeParityTests(unittest.TestCase):
    SOURCE = (
        "fn main() { "
        f"println({INT_MAX}) "
        f"println({INT_MIN}) "
        f'let add = {INT_MAX} + 1 or "ADD-OVERFLOW" '
        f'let sub = {INT_MIN} - 1 or "SUB-OVERFLOW" '
        f'let mul = {INT_MAX} * 2 or "MUL-OVERFLOW" '
        f'let neg = -({INT_MIN}) or "NEG-OVERFLOW" '
        'println("{add} {sub} {mul} {neg}") '
        "}"
    )

    def _interpreter_output(self, path: pathlib.Path) -> str:
        result = subprocess.run(
            ["python3", "-m", "koschei", "run", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def _native_output(self, path: pathlib.Path) -> str:
        program = parse(path.read_text(encoding="utf-8"))
        check(program)
        generated = generate_go(program)
        with tempfile.TemporaryDirectory(prefix="koschei-int64-go-") as workspace:
            directory = pathlib.Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheiint64\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "program"
            build = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            return run.stdout

    def test_checked_int64_matches_interpreter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-int64-src-") as workspace:
            path = pathlib.Path(workspace) / "int64.ks"
            path.write_text(self.SOURCE, encoding="utf-8")
            interpreted = self._interpreter_output(path)
            native = self._native_output(path)

        self.assertEqual(native, interpreted)
        self.assertIn(str(INT_MAX), interpreted)
        self.assertIn(str(INT_MIN), interpreted)
        self.assertIn(
            "ADD-OVERFLOW SUB-OVERFLOW MUL-OVERFLOW NEG-OVERFLOW",
            interpreted,
        )


if __name__ == "__main__":
    unittest.main()
