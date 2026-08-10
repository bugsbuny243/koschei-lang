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
FINANCIAL_ROOT = REPO_ROOT / "examples" / "financial_exchange"
ENTRY = FINANCIAL_ROOT / "main.ks"
EXPECTED = (
    "TRADE maker=S-0001 taker=B-0001 price_ticks=10100 quantity_lots=25\n"
    "NO_TRADE\n"
    "NO_TRADE\n"
)
GO_BINARY = shutil.which("go")


class FinancialMatchingKernelTests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"financial kernel interpreter exit: {code}")
        return output.getvalue()

    def test_financial_sources_never_use_float(self) -> None:
        for path in sorted(FINANCIAL_ROOT.glob("*.ks")):
            with self.subTest(path=path.name):
                tokens = tokenize(path.read_text(encoding="utf-8"))
                float_literals = [
                    token
                    for token in tokens
                    if token.type is TokenType.NUMBER and isinstance(token.value, float)
                ]
                float_types = [
                    token
                    for token in tokens
                    if token.type is TokenType.TYPE and token.value == "Float"
                ]
                self.assertEqual(float_literals, [], "financial core cannot use Float literals")
                self.assertEqual(float_types, [], "financial core cannot declare Float")

    def test_matching_core_has_zero_side_effect_authority(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        manifest = analyze_graph(graph)
        self.assertEqual(manifest.grants, ())
        self.assertEqual(manifest.holder_functions, ())

    def test_price_time_result_is_deterministic(self) -> None:
        first = self.interpreter_output()
        second = self.interpreter_output()
        self.assertEqual(first, EXPECTED)
        self.assertEqual(second, EXPECTED)
        self.assertEqual(first, second)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_native_binary_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go(graph.root_module.program, graph)

        with tempfile.TemporaryDirectory(prefix="koschei-financial-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheifinancial\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "matching-kernel"
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
