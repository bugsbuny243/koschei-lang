"""`ks run` keeps the checked-AST interpreter only for real AST boundaries.

A sealed graph without ``MirAstFallback`` runs on sealed MIR (the direct MIR
runtime or the canonical MIR executor), so the binary from ``ks build`` and
``ks run`` follow the same executor rules. The host interpreter also has
enough recursion headroom to reach Koschei's own call-depth limit.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from koschei import runtime_budget
from koschei.ast_nodes import SourceLocation
from koschei.canonical_mir_budget_runtime_v1 import canonical_mir_complete_v1
from koschei.cli_entry import main
from koschei.mir_ir import MirAstFallback, MirConst
from koschei.type_system import NamedType

DEPTH_PROGRAM = """
fn down(n: Int) -> Int {
    if n == 0 {
        return 0
    }
    return down(n - 1) + 1
}

fn main() {
{marker}    println(down({depth}))
}
"""

LANE_MARKERS = {
    "direct": "",
    "canonical variant facts": "    let marker = Some(1)\n",
    "canonical member calls": '    let marker = "x".length()\n',
}


def _graph(instruction) -> SimpleNamespace:
    block = SimpleNamespace(instructions=(instruction,))
    function = SimpleNamespace(blocks=(block,))
    module = SimpleNamespace(functions=(function,))
    return SimpleNamespace(in_dependency_order=lambda: [module], modules={"root": module})


class SingleRuntimeAuthorityTests(unittest.TestCase):
    def run_source(self, source: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory(prefix="koschei-authority-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["run", str(path)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_member_calls_without_variant_facts_never_reach_the_ast_interpreter(self) -> None:
        source = (
            "fn main() {\n"
            '    let names = "ali,ayşe".split(",")\n'
            "    let max = 9223372036854775807\n"
            "    let values = [1, max + 1, 3]\n"
            "    println(names.length())\n"
            "    println(values)\n"
            "    println(values.length())\n"
            "}\n"
        )
        with patch.object(
            runtime_budget,
            "BudgetedInterpreter",
            side_effect=AssertionError("checked-AST interpreter must not run"),
        ):
            code, output, errors = self.run_source(source)
        self.assertEqual(code, 0, errors)
        # Sealed MIR keeps the Error as a list element, exactly like `ks build`.
        self.assertEqual(
            output,
            "2\n[1, KS3501: Int taşması: '+' işlemi işaretli 64-bit aralığın "
            "dışına çıktı., 3]\n3\n",
        )

    def test_only_graphs_with_an_ast_boundary_are_left_to_the_ast_interpreter(self) -> None:
        location = SourceLocation(1, 1)
        fallback = _graph(MirAstFallback(None, "ForBind", NamedType("Void"), location))
        self.assertFalse(canonical_mir_complete_v1(fallback))
        with patch(
            "koschei.canonical_mir_budget_runtime_v1.require_mir_v4_graph_registry",
            return_value=None,
        ):
            self.assertTrue(
                canonical_mir_complete_v1(_graph(MirConst(1, 1, NamedType("Int"), location)))
            )
        with patch(
            "koschei.canonical_mir_budget_runtime_v1.require_mir_v4_graph_registry",
            side_effect=ValueError("unregistered MIR v4 instruction class"),
        ):
            self.assertFalse(
                canonical_mir_complete_v1(_graph(MirConst(1, 1, NamedType("Int"), location)))
            )

    def test_every_lane_reaches_the_language_call_depth_limit(self) -> None:
        for lane, marker in LANE_MARKERS.items():
            with self.subTest(lane):
                code, output, errors = self.run_source(
                    DEPTH_PROGRAM.replace("{marker}", marker).replace("{depth}", "510")
                )
                self.assertEqual((code, output), (0, "510\n"), errors)

    def test_every_lane_stops_beyond_the_limit_with_a_koschei_diagnostic(self) -> None:
        for lane, marker in LANE_MARKERS.items():
            with self.subTest(lane):
                code, output, errors = self.run_source(
                    DEPTH_PROGRAM.replace("{marker}", marker).replace("{depth}", "511")
                )
                self.assertEqual((code, output), (1, ""))
                self.assertNotIn("RecursionError", errors)
                self.assertTrue("KS3602" in errors or "KS3105" in errors, errors)

    def test_host_recursion_limit_is_restored_after_a_run(self) -> None:
        before = sys.getrecursionlimit()
        self.run_source(DEPTH_PROGRAM.replace("{marker}", "").replace("{depth}", "3"))
        self.assertEqual(sys.getrecursionlimit(), before)


if __name__ == "__main__":
    unittest.main()
