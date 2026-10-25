"""A local binding shadows a function of the same name in every executor.

Sealed MIR always resolved `let digest = ...` before the function `digest`.
The checked-AST interpreter resolved the function first and crashed with a
host TypeError (`'GenericFunctionDeclaration' + int`). The Core Library's own
`secure.hash` binds a local named `digest`, so this decided whether library
code could run on that lane at all.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli_main
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget

PROGRAM = """
import secure

fn helper() -> Int {
    return 1
}

fn main() {
    let helper = 5
    println(helper + 1)
    let digest = secure.hash("abc") or "?"
    println(digest)
}
"""

EXPECTED = (
    "6\n"
    "sha3-256:3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532\n"
)


class LocalShadowingTests(unittest.TestCase):
    def graph(self):
        temporary = tempfile.TemporaryDirectory(prefix="koschei-shadowing-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(PROGRAM, encoding="utf-8")
        return path

    def test_every_executor_prefers_the_local_binding(self) -> None:
        path = self.graph()
        graph = load_graph(path)
        check_graph(graph)
        mir = graph.mir
        root = mir.root_module

        checked = io.StringIO()
        with redirect_stdout(checked):
            BudgetedInterpreter(
                root.program,
                [],
                namespaces=mir.namespaces(),
                imports=dict(root.imports),
                enums=mir.enums(),
                module_imports=mir.module_imports(),
                structs=mir.structs(),
                budget=runtime_budget.RuntimeBudget(),
            ).execute_main()

        canonical = io.StringIO()
        with redirect_stdout(canonical):
            _run_budgeted_canonical_mir(mir, [], RuntimeBudget())

        public = io.StringIO()
        with redirect_stdout(public), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())

        self.assertEqual(checked.getvalue(), EXPECTED)
        self.assertEqual(canonical.getvalue(), EXPECTED)
        self.assertEqual(public.getvalue(), EXPECTED)


if __name__ == "__main__":
    unittest.main()
