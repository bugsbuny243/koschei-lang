"""Every executor behind `ks run` must compute the same output.

The same program is run explicitly on the direct MIR runtime (when it admits
the graph), the canonical MIR executor and the checked-AST compatibility
interpreter, and through `ks run` itself, whichever lane it selects.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph

OVERFLOWS = """
fn main() {
    let max = 9223372036854775807
    let min = 0 - max - 1
    println(max + 1)
    println(min - 1)
    println(max * 2)
    println(min / -1)
    println(-min)
{extra}}
"""


def _expected(operations: tuple[str, ...]) -> str:
    return "".join(
        f"KS3501: Int taşması: '{operation}' işlemi işaretli 64-bit aralığın dışına çıktı.\n"
        for operation in operations
    )


class ExecutorConsistencyTests(unittest.TestCase):
    def outputs(self, source: str) -> dict[str, str]:
        results: dict[str, str] = {}
        with tempfile.TemporaryDirectory(prefix="koschei-lanes-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)
            mir = graph.mir
            root = mir.root_module
            runs = {
                "ks run": lambda: main(["run", str(path)]),
                "canonical": lambda: _run_budgeted_canonical_mir(
                    mir, [], runtime_budget.RuntimeBudget()
                ),
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
            }
            if inspect_native_mir_support(mir).supported:
                runs["direct"] = lambda: run_mir_native(mir)
            for name, run in runs.items():
                stdout = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                    with runtime_budget.host_recursion_headroom():
                        run()
                results[name] = stdout.getvalue()
        return results

    def assert_all(self, source: str, expected: str, *, direct: bool) -> None:
        outputs = self.outputs(source)
        self.assertEqual("direct" in outputs, direct)
        for name, output in outputs.items():
            with self.subTest(executor=name):
                self.assertEqual(output, expected)

    def test_int_overflow_text_is_identical_in_every_executor(self) -> None:
        operations = ("+", "-", "*", "/", "unary -")
        self.assert_all(OVERFLOWS.replace("{extra}", ""), _expected(operations), direct=True)
        # The direct runtime does not admit '%'; every other executor must agree.
        self.assert_all(
            OVERFLOWS.replace("{extra}", "    println(min % -1)\n"),
            _expected((*operations, "%")),
            direct=False,
        )

    def test_enum_values_render_canonically_in_every_executor(self) -> None:
        source = (
            "fn wrap(value: Int) -> Option<Int> {\n    return Some(value)\n}\n\n"
            "fn main() {\n    let none: Option<Int> = None()\n"
            "    println(wrap(3))\n    println(none)\n    println([wrap(1), none])\n}\n"
        )
        self.assert_all(source, "Some(3)\nNone\n[Some(1), None]\n", direct=True)


if __name__ == "__main__":
    unittest.main()
