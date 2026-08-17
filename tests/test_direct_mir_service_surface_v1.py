from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_native_runtime import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph
from koschei.workspace import load_workspace
from koschei.workspace_modules import load_workspace_member_graph


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "examples" / "production_reference_v1"
EXPECTED_OUTPUT = (
    "trade quantity=25 price=10100 notional=252500 buyer_cash=-252626 seller_cash=252450 fees=176 balanced=true\n"
    "trade quantity=0 price=10100 notional=0 buyer_cash=0 seller_cash=0 fees=0 balanced=true\n"
    "trade quantity=0 price=10100 notional=0 buyer_cash=0 seller_cash=0 fees=0 balanced=true\n"
    '{"a":1,"b":2}\n'
    "30\n"
)


class DirectMirServiceSurfaceV1Tests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_integer_division_matches_koschei_truncate_toward_zero_contract(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    println(7 / 2)
    println(-7 / 2)
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), "3\n-3\n")

    def test_interpolation_executes_without_ast_compatibility(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let quantity = 25
    let balanced = true
    println("quantity={quantity} balanced={balanced}")
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), "quantity=25 balanced=true\n")

    def test_order_worker_full_dependency_graph_executes_from_direct_mir(self) -> None:
        workspace = load_workspace(REFERENCE)
        self.assertEqual(len(workspace.members), 12)

        graph = load_workspace_member_graph(workspace, "order_worker")
        check_graph(graph)
        self.assertEqual(len(graph.modules), 11)

        mir = require_mir(graph)
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), EXPECTED_OUTPUT)


if __name__ == "__main__":
    unittest.main()
