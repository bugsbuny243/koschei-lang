"""`ks run` routes a program to one of three executors; they must agree.

* direct MIR (``mir_native_v1``): no member calls and no ``%``;
* canonical MIR: Option/Result/enum facts plus member calls;
* checked-AST compatibility: member calls without variant facts.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import _requires_canonical_mir_runtime_v1, runtime_execution_mode

OVERFLOWS = """
    let max = 9223372036854775807
    let min = 0 - max - 1
    println(max + 1)
    println(min - 1)
    println(max * 2)
    println(min / -1)
    println(-min)
"""
MODULO = "    println(min % -1)\n"


def _expected(operations: tuple[str, ...]) -> str:
    return "".join(
        f"KS3501: Int taşması: '{operation}' işlemi işaretli 64-bit aralığın dışına çıktı.\n"
        for operation in operations
    )


LANES = {
    # No member call and no variant fact: direct MIR runtime.
    "direct": "",
    # A variant fact plus a member call: canonical MIR executor.
    "canonical": '    let marker = Some("x".length())\n',
    # A member call without variant facts: checked-AST compatibility.
    "ast": '    let marker = "x".length()\n',
}


class ExecutorConsistencyTests(unittest.TestCase):
    def run_source(self, source: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory(prefix="koschei-lanes-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)
            # Same routing order as runtime_budget.run_mir_with_budget.
            if runtime_execution_mode(graph.mir) == "mir_native_v1":
                lane = "direct"
            elif _requires_canonical_mir_runtime_v1(graph.mir):
                lane = "canonical"
            else:
                lane = "ast"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["run", str(path)])
        self.assertEqual(code, 0, stderr.getvalue())
        return lane, stdout.getvalue()

    def test_int_overflow_text_is_identical_in_every_lane(self) -> None:
        operations = ("+", "-", "*", "/", "unary -")
        for expected_lane, marker in LANES.items():
            with self.subTest(expected_lane):
                lane, output = self.run_source(f"fn main() {{\n{marker}{OVERFLOWS}}}\n")
                self.assertEqual(lane, expected_lane)
                self.assertEqual(output, _expected(operations))
        # The direct runtime does not admit '%'; the other two lanes must agree.
        for expected_lane in ("canonical", "ast"):
            with self.subTest(f"{expected_lane} %"):
                marker = LANES[expected_lane]
                lane, output = self.run_source(
                    f"fn main() {{\n{marker}{OVERFLOWS}{MODULO}}}\n"
                )
                self.assertEqual(lane, expected_lane)
                self.assertEqual(output, _expected((*operations, "%")))

    def test_direct_mir_lane_renders_enum_values_canonically(self) -> None:
        source = (
            "fn wrap(value: Int) -> Option<Int> {\n    return Some(value)\n}\n\n"
            "fn main() {\n    let none: Option<Int> = None()\n"
            "    println(wrap(3))\n    println(none)\n    println([wrap(1), none])\n}\n"
        )
        lane, output = self.run_source(source)
        self.assertEqual(lane, "direct")
        self.assertEqual(output, "Some(3)\nNone\n[Some(1), None]\n")


if __name__ == "__main__":
    unittest.main()
