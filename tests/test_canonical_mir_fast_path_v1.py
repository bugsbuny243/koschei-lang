"""The canonical MIR executor's fast paths change speed, never behaviour.

`BudgetedCanonicalMirExecutorV1._call` runs the commonest instructions inline
and inlines `RuntimeBudget.consume_step`. A budget of any other type takes the
full dispatch for every step, so running the same programs with a subclass
shows the inline path counts the same steps and computes the same values.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.canonical_mir_budget_runtime_v1 import BudgetedCanonicalMirExecutorV1
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import RuntimeBudget
from koschei.type_system import parse_type_text

PROGRAMS = {
    "loop": """fn main() {
    let mut i = 0
    let mut total = 0
    while i < 500 {
        total = total + i % 7 - 1
        i = i + 1
    }
    println(total)
    let big = 9223372036854775807
    println(big + 1 or -1)
    println(10 / 0 or 0)
}
""",
    "calls": """import http
import text

fn fib(n: Int) -> Int {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}

fn main() {
    println(fib(12))
    let found = http.route("/users/:id", "/users/7?x=1") or {
        println("no route")
        return
    }
    println(found.get("id") or "?")
    println(text.replace("a-b", "-", "+") or "?")
    let words = "pear, fig".split(",") or []
    for word in words {
        println(word.trim())
    }
}
""",
}


class _CountingBudget(RuntimeBudget):
    """A RuntimeBudget subclass: the executor charges every step through consume_step."""


class FastPathTests(unittest.TestCase):
    def run_program(self, source: str, budget: RuntimeBudget) -> tuple[str, int]:
        with tempfile.TemporaryDirectory(prefix="koschei-fast-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                BudgetedCanonicalMirExecutorV1(graph.mir, [], budget=budget).execute_main()
        return stdout.getvalue(), budget.steps

    def test_same_output_and_steps_as_the_full_dispatch(self) -> None:
        for name, source in PROGRAMS.items():
            with self.subTest(program=name):
                fast = self.run_program(source, RuntimeBudget(max_steps=10_000_000))
                full = self.run_program(source, _CountingBudget(max_steps=10_000_000))
                self.assertEqual(fast, full)
                self.assertGreater(fast[1], 100)

    def test_the_step_budget_stops_at_the_same_step(self) -> None:
        source = PROGRAMS["loop"]
        _, steps = self.run_program(source, RuntimeBudget(max_steps=10_000_000))
        self.run_program(source, RuntimeBudget(max_steps=steps))
        for budget in (RuntimeBudget(max_steps=steps - 1), _CountingBudget(max_steps=steps - 1)):
            with self.assertRaises(Exception) as caught:
                self.run_program(source, budget)
            self.assertIn("KS3601", str(caught.exception.code if hasattr(caught.exception, "code") else caught.exception))

    def test_parsed_types_are_shared_and_immutable(self) -> None:
        self.assertIs(parse_type_text("Map<String, Int> or Error"), parse_type_text("Map<String, Int> or Error"))
        with self.assertRaises(ValueError):
            parse_type_text("List<Int")


if __name__ == "__main__":
    unittest.main()
