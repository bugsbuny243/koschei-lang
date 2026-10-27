"""Struct values have value semantics in every executor.

A field assignment on a ``let mut`` binding changes that binding only. Before
this rule every executor mutated the shared struct object in place, so
``let a = P {..}; let mut b = a; b.x = 2`` also changed the immutable ``a``,
and a callee that copied a parameter into ``let mut`` changed its caller's
value and every List holding it.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli_main
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget, runtime_execution_mode

PROGRAM = """
struct P {
    x: Int,
    name: String,
}

fn bump(p: P) -> Int {
    let mut q = p
    q.x = q.x + 100
    return q.x
}

fn rename(p: P, name: String) -> P {
    let mut q = p
    q.name = name
    return q
}

fn main() {
    let a = P { x: 1, name: "a" }
    let mut b = a
    b.x = 2
    println("{a} {b}")
    let items = [b]
    b.x = 3
    println("{items} {b}")
    println("{bump(b)} {b}")
    let renamed = rename(b, "z")
    println("{renamed} {b} {renamed == b}")
    let mut c = b
    c.x = c.x + 0
    println("{c == b}")
    for item in items {
        let mut copy = item
        copy.x = 0
    }
    let mut d = b
    d.name = "q"
    d.x = 9
    println("{d} {items}")
}
"""

EXPECTED = (
    'P { x: 1, name: "a" } P { x: 2, name: "a" }\n'
    '[P { x: 2, name: "a" }] P { x: 3, name: "a" }\n'
    '103 P { x: 3, name: "a" }\n'
    'P { x: 3, name: "z" } P { x: 3, name: "a" } false\n'
    "true\n"
    'P { x: 9, name: "q" } [P { x: 2, name: "a" }]\n'
)


class StructValueSemanticsTests(unittest.TestCase):
    def program(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-struct-values-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(PROGRAM, encoding="utf-8")
        return path

    def test_ks_run(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(self.program())])
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), EXPECTED)

    def test_canonical_mir_executor(self) -> None:
        graph = load_graph(self.program())
        check_graph(graph)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_budgeted_canonical_mir(graph.mir, [], RuntimeBudget())
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), EXPECTED)

    def test_checked_ast_interpreter(self) -> None:
        graph = load_graph(self.program())
        check_graph(graph)
        mir = graph.mir
        root = mir.root_module
        stdout = io.StringIO()
        with redirect_stdout(stdout):
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
        self.assertEqual(stdout.getvalue(), EXPECTED)

    def test_direct_mir_runtime_renders_structs_canonically(self) -> None:
        # No member calls, imports or field assignment: `ks run` takes the
        # direct MIR runtime, which used to print its host representation
        # (`_StructValue(type_name='P', ...)`).
        source = (
            "struct P {\n    x: Int,\n    name: String,\n}\n\n"
            "fn main() {\n    let p = P { x: 1, name: \"a\" }\n    println(p)\n"
            '    println("{[p]} {p == p}")\n}\n'
        )
        path = self.program()
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        self.assertEqual(runtime_execution_mode(graph.mir), "mir_native_v1")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(path)])
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(
            stdout.getvalue(), 'P { x: 1, name: "a" }\n[P { x: 1, name: "a" }] true\n'
        )

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is required")
    def test_native_binary(self) -> None:
        path = self.program()
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["build", str(path), "-o", str(binary)])
        self.assertEqual(code, 0, errors.getvalue())
        completed = subprocess.run([str(binary)], capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.decode("utf-8"), EXPECTED)


if __name__ == "__main__":
    unittest.main()
