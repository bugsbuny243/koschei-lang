from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import build_parser, main
from koschei.interpreter import KoscheiRuntimeError
from koschei.modules import check_graph, load_graph
from koschei.mir import require_mir
from koschei.runtime_budget import RuntimeBudget, run_mir_with_budget


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


class RuntimeBudgetTests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source.strip() + "\n", encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_real_koschei_project_runs_under_explicit_budget(self) -> None:
        graph = load_graph(EXAMPLES / "runtime_budget.ks")
        check_graph(graph)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir_with_budget(
                require_mir(graph), max_steps=500, max_call_depth=32
            )
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "0\nruntime budget ready\n")

    def test_infinite_loop_is_stopped_by_step_budget(self) -> None:
        mir = self.checked_mir("fn main() { while true {} }")
        with self.assertRaises(KoscheiRuntimeError) as caught:
            run_mir_with_budget(mir, max_steps=25, max_call_depth=32)
        self.assertEqual(caught.exception.code, "KS3601")

    def test_recursion_bomb_is_stopped_by_user_depth_budget(self) -> None:
        mir = self.checked_mir(
            """
            fn dive(value: Int) -> Int {
                return dive(value + 1)
            }
            fn main() {
                println(dive(0))
            }
            """
        )
        with self.assertRaises(KoscheiRuntimeError) as caught:
            run_mir_with_budget(mir, max_steps=10_000, max_call_depth=8)
        self.assertEqual(caught.exception.code, "KS3602")

    def test_budget_rejects_non_positive_or_above_hard_depth(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeBudget(max_steps=0)
        with self.assertRaises(ValueError):
            RuntimeBudget(max_call_depth=513)


class RuntimeBudgetCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(argv)
        return code, output.getvalue(), error.getvalue()

    def test_run_help_exposes_budgets(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            build_parser().parse_args(["run", "--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("--max-steps", output.getvalue())
        self.assertIn("--max-call-depth", output.getvalue())

    def test_cli_runs_real_project_with_budgets(self) -> None:
        code, output, error = self.run_cli(
            [
                "run",
                str(EXAMPLES / "runtime_budget.ks"),
                "--max-steps",
                "500",
                "--max-call-depth",
                "32",
            ]
        )
        self.assertEqual(code, 0, error)
        self.assertIn("runtime budget ready", output)

    def test_cli_infinite_loop_attack_reports_ks3601(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text("fn main() { while true {} }\n", encoding="utf-8")
            code, _, error = self.run_cli(
                ["run", str(path), "--max-steps", "20"]
            )
        self.assertEqual(code, 1)
        self.assertIn("KS3601", error)

    def test_cli_recursion_attack_reports_ks3602(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(
                "fn dive(n: Int) -> Int { return dive(n + 1) }\n"
                "fn main() { println(dive(0)) }\n",
                encoding="utf-8",
            )
            code, _, error = self.run_cli(
                ["run", str(path), "--max-call-depth", "6"]
            )
        self.assertEqual(code, 1)
        self.assertIn("KS3602", error)

    def test_cli_rejects_invalid_budget_values(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit):
            build_parser().parse_args(["run", "app.ks", "--max-steps", "0"])
        with redirect_stderr(error), self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["run", "app.ks", "--max-call-depth", "513"]
            )
        self.assertIn("positive integer", error.getvalue())
        self.assertIn("cannot exceed 512", error.getvalue())

    def test_explain_knows_budget_diagnostics(self) -> None:
        code, output, error = self.run_cli(["--lang", "en", "explain", "KS3601"])
        self.assertEqual(code, 0, error)
        self.assertIn("Execution step budget exhausted", output)


if __name__ == "__main__":
    unittest.main()
