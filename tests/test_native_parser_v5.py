from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.lexer import LexerError
from koschei.parser import ParserError, parse


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
class NativeParserV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        executable = "ksc-native.exe" if os.name == "nt" else "ksc-native"
        cls.native_binary = Path(cls._temporary_directory.name) / executable
        build = subprocess.run(
            ["go", "build", "-trimpath", "-o", str(cls.native_binary), "./cmd/ksc-native"],
            cwd=ROOT / "native",
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def _native(self, source: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.native_binary), "--ast", *arguments],
            input=source,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_ast_schema_is_versioned_and_literals_are_exact(self) -> None:
        source = '''
struct Box<T> { value: T }
fn main() {
    let empty = ""
    let precise = 1.0000000000000001
    return Box { value: precise }
}
'''
        native = self._native(source)
        self.assertEqual(native.returncode, 0, native.stderr)
        document = json.loads(native.stdout)
        self.assertEqual(document["schema"], "koschei.syntax/v1")
        self.assertEqual(document["kind"], "Program")
        self.assertEqual(document["structs"][0]["type_parameters"][0]["name"], "T")
        statements = document["functions"][0]["body"]["statements"]
        self.assertEqual(statements[0]["value"]["literal"]["text"], "")
        self.assertEqual(
            statements[1]["value"]["literal"]["text"],
            "1.0000000000000001",
        )

    def test_checked_in_parser_acceptance_matches_python(self) -> None:
        sources = sorted(
            path
            for path in ROOT.rglob("*.ks")
            if ".git" not in path.parts and "__pycache__" not in path.parts
        )
        self.assertGreaterEqual(len(sources), 10, "expected a meaningful .ks corpus")
        for path in sources:
            source = path.read_text(encoding="utf-8")
            try:
                parse(source)
            except (LexerError, ParserError, SyntaxError, ValueError) as error:
                python_failure = str(error)
            else:
                python_failure = None
            native = self._native(source)
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(
                    native.returncode == 0,
                    python_failure is None,
                    "parser acceptance diverged\n"
                    f"python_error={python_failure!r}\n"
                    f"native_stdout={native.stdout!r}\n"
                    f"native_stderr={native.stderr!r}",
                )

    def test_output_is_deterministic(self) -> None:
        source = 'fn main() { println("value={1 + 2}") }'
        first = self._native(source)
        second = self._native(source)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_parser_budgets_fail_closed_with_locations(self) -> None:
        node_budget = self._native("fn main() {}", "--max-nodes", "1")
        self.assertEqual(node_budget.returncode, 1)
        self.assertIn("node budget exhausted", node_budget.stderr)
        self.assertRegex(node_budget.stderr, r"\[line \d+, column \d+\]")

        depth_budget = self._native(
            "fn main() { return [[1]] }",
            "--max-depth",
            "3",
        )
        self.assertEqual(depth_budget.returncode, 1)
        self.assertIn("depth budget exhausted", depth_budget.stderr)
        self.assertRegex(depth_budget.stderr, r"\[line \d+, column \d+\]")

    def test_ast_mode_rejects_comment_token_output(self) -> None:
        result = self._native("fn main() {}", "--comments")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--comments is only valid in token mode", result.stderr)


if __name__ == "__main__":
    unittest.main()
