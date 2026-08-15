from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.capabilities import analyze_graph
from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go
from koschei.lexer import TokenType, tokenize
from koschei.modules import check_graph, load_graph


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "financial_exchange" / "order_book_v1.ks"
EXPECTED = (
    "0\n"
    "1\n"
    "S2\n"
    "10050\n"
    "1\n"
    "5\n"
    "7\n"
    "10\n"
    "duplicate-rejected\n"
    "10\n"
    "self-trade-rejected\n"
    "1\n"
)
GO_BINARY = shutil.which("go")


class FinancialOrderBookV1Tests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"order book interpreter exit: {code}")
        return output.getvalue()

    def test_order_book_source_never_uses_float(self) -> None:
        tokens = tokenize(ENTRY.read_text(encoding="utf-8"))
        self.assertFalse(
            any(
                token.type is TokenType.NUMBER and isinstance(token.value, float)
                for token in tokens
            )
        )
        self.assertFalse(
            any(
                token.type is TokenType.TYPE and token.value == "Float"
                for token in tokens
            )
        )

    def test_order_book_core_has_zero_side_effect_authority(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        manifest = analyze_graph(graph)
        self.assertFalse(manifest.grants)
        self.assertFalse(manifest.holder_functions)
        self.assertEqual(manifest.domains(), [])

    def test_order_book_scenario_is_byte_deterministic(self) -> None:
        first = self.interpreter_output()
        second = self.interpreter_output()
        third = self.interpreter_output()
        self.assertEqual(first, EXPECTED)
        self.assertEqual(second, EXPECTED)
        self.assertEqual(third, EXPECTED)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_reference_covers_p2_policy_failure_modes(self) -> None:
        source = ENTRY.read_text(encoding="utf-8")
        for code in ("KS3810", "KS3811", "KS3812", "KS3813", "KS3814", "KS3815"):
            with self.subTest(code=code):
                self.assertIn(code, source)
        for function in (
            "submit_order",
            "cancel_order",
            "replace_order",
            "self_trade_preflight",
            "insert_bid",
            "insert_ask",
        ):
            with self.subTest(function=function):
                self.assertIn(f"fn {function}", source)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_native_binary_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go(graph.root_module.program, graph)

        with tempfile.TemporaryDirectory(prefix="koschei-order-book-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheiorderbook\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "order-book-v1"
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
