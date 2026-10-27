"""Titan: the KS3502 value size budget in every executor.

A String holds at most 16 MiB of UTF-8 and a List at most 1,048,576 items.
The programs here sit exactly on each bound and one step past it, and must
print the same bytes on the canonical MIR executor (`ks run`), the checked-AST
interpreter, the direct MIR runtime and a MIR-Go binary.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from koschei import runtime_budget
from koschei.cli_entry import main as cli_main
from koschei.diagnostics import CATALOG, ENGLISH_CATALOG
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget, runtime_execution_mode
from koschei.value_budget_v1 import (
    LIST_MESSAGE,
    MAX_LIST_ITEMS,
    MAX_STRING_BYTES,
    STRING_MESSAGE,
    fits_texts,
    join_fits,
    oversize_message,
    split_fits,
)

GO = shutil.which("go")
REPOSITORY = Path(__file__).resolve().parents[1]

DOUBLED = """
fn doubled(seed: String, times: Int) -> String {
    let mut value = seed
    let mut index = 0
    while index < times {
        value = value + value
        index = index + 1
    }
    return value
}
"""

BOUNDARIES = DOUBLED + """
fn main() {
    let full = doubled("a", 24)
    println(full.length())
    let over = full + "a"
    let caught = over or "STOP"
    println(caught.length())
    println(over)
    let wide = doubled("ç", 23)
    println(wide.length())
    let wider = wide + "ç" or "STOP"
    println(wider)
    let half = doubled("a", 23)
    let pair = "{half}{half}"
    println(pair.length())
    let more = "{half}{half}!" or "STOP"
    println(more)
    let separator = doubled("a", 14)
    let mut items: List<String> = []
    let mut index = 0
    while index < 1025 {
        items = items.push("")
        index = index + 1
    }
    let joined = separator.join(items) or "STOP"
    println(joined.length())
    items = items.push("")
    let too_long = separator.join(items) or "STOP"
    println(too_long)
    let mut commas = ""
    let mut step = ","
    let mut bit = 0
    while bit < 20 {
        commas = commas + step
        step = step + step
        bit = bit + 1
    }
    let pieces = commas.split(",")
    println(pieces.length())
    let limit = pieces.push("x")
    println(limit)
    let too_many = (commas + ",").split(",")
    println(too_many)
}
"""

BOUNDARIES_OUTPUT = "\n".join(
    [
        str(MAX_STRING_BYTES),
        "4",
        STRING_MESSAGE,
        str(MAX_STRING_BYTES // 2),
        "STOP",
        str(MAX_STRING_BYTES),
        "STOP",
        str(MAX_STRING_BYTES),
        "STOP",
        str(MAX_LIST_ITEMS),
        LIST_MESSAGE,
        LIST_MESSAGE,
    ]
) + "\n"

# No member call: `ks run` takes the direct MIR runtime for this one.
DIRECT = """
fn main() {
    let mut value = "a"
    let mut index = 0
    while index < 25 {
        value = value + value
        index = index + 1
    }
    let fallback = value or "STOP"
    println(fallback)
    println("{value}")
    let ok = "a" + "b"
    println("{ok}{ok}")
}
"""


class ValueBudgetTests(unittest.TestCase):
    def write(self, source: str, name: str = "main.ks") -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-titan-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / name
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(path)])
        self.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue()

    def test_helpers_count_utf8_bytes(self) -> None:
        self.assertTrue(fits_texts(["a" * MAX_STRING_BYTES]))
        self.assertFalse(fits_texts(["a" * MAX_STRING_BYTES, "a"]))
        self.assertTrue(fits_texts(["ç" * (MAX_STRING_BYTES // 2)]))
        self.assertFalse(fits_texts(["ç" * (MAX_STRING_BYTES // 2) + "a"]))
        self.assertTrue(join_fits("ab", ["", "", ""]))
        self.assertFalse(join_fits("a" * 16384, [""] * 1026))
        self.assertTrue(join_fits("a" * 16384, [""] * 1025))
        self.assertTrue(split_fits("," * (MAX_LIST_ITEMS - 1), ","))
        self.assertFalse(split_fits("," * MAX_LIST_ITEMS, ","))
        self.assertEqual(oversize_message([0] * (MAX_LIST_ITEMS + 1)), LIST_MESSAGE)
        self.assertIsNone(oversize_message([0] * MAX_LIST_ITEMS))
        self.assertIsNone(oversize_message(7))

    def test_diagnostic_is_cataloged_in_both_languages(self) -> None:
        self.assertEqual(CATALOG["KS3502"].title, "Bellek bütçesi aşıldı")
        self.assertEqual(ENGLISH_CATALOG["KS3502"].title, "Memory budget exceeded")
        for catalog in (CATALOG, ENGLISH_CATALOG):
            self.assertIn(str(MAX_STRING_BYTES), catalog["KS3502"].why)
            self.assertIn(str(MAX_LIST_ITEMS), catalog["KS3502"].why)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(cli_main(["explain", "KS3502"]), 0)
        self.assertIn("KS3502", stdout.getvalue())

    def test_ks_run_stops_on_every_bound(self) -> None:
        self.assertEqual(self.ks_run(self.write(BOUNDARIES)), BOUNDARIES_OUTPUT)

    def test_checked_ast_interpreter_agrees(self) -> None:
        graph = load_graph(self.write(BOUNDARIES))
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
                budget=runtime_budget.RuntimeBudget(max_steps=50_000_000),
            ).execute_main()
        self.assertEqual(stdout.getvalue(), BOUNDARIES_OUTPUT)

    def test_direct_mir_runtime_agrees(self) -> None:
        path = self.write(DIRECT)
        graph = load_graph(path)
        check_graph(graph)
        self.assertEqual(runtime_execution_mode(graph.mir), "mir_native_v1")
        self.assertEqual(self.ks_run(path), f"STOP\n{STRING_MESSAGE}\nabab\n")

    @unittest.skipUnless(GO, "Go toolchain is required")
    def test_native_binary_agrees(self) -> None:
        for source in (BOUNDARIES, DIRECT):
            with self.subTest(source=source[:40]):
                path = self.write(source)
                binary = path.parent / "app"
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    code = cli_main(["build", str(path), "-o", str(binary)])
                self.assertEqual(code, 0, errors.getvalue())
                completed = subprocess.run(
                    [str(binary)], capture_output=True, timeout=120, check=False
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.decode("utf-8"), self.ks_run(path))

    def test_disk_read_obeys_the_string_budget(self) -> None:
        path = self.write(
            "fn main(caps: SystemCaps) {\n"
            '    let disk = caps.disk.allow_read_only(".") or return\n'
            '    let exact = disk.read("exact.txt") or "STOP"\n'
            "    println(exact.length())\n"
            '    let big = disk.read("big.txt") or "STOP"\n'
            "    println(big)\n"
            '    let wide = disk.read("wide.txt")\n'
            "    println(wide)\n"
            "}\n"
        )
        (path.parent / "exact.txt").write_text("a" * MAX_STRING_BYTES, encoding="utf-8")
        (path.parent / "big.txt").write_text("a" * (MAX_STRING_BYTES + 1), encoding="utf-8")
        (path.parent / "wide.txt").write_text(
            "ç" * (MAX_STRING_BYTES // 2 + 1), encoding="utf-8"
        )
        previous = os.getcwd()
        os.chdir(path.parent)
        try:
            output = self.ks_run(path)
        finally:
            os.chdir(previous)
        self.assertEqual(output, f"{MAX_STRING_BYTES}\nSTOP\n{STRING_MESSAGE}\n")

    @unittest.skipUnless(sys.platform.startswith("linux"), "RLIMIT_AS is Linux-specific here")
    def test_host_memory_exhaustion_is_a_koschei_stop(self) -> None:
        # Every value stays within its own budget; together they exceed the
        # host limit. `ks run` must stop with KS3502, not a Python traceback.
        path = self.write(
            DOUBLED
            + "\nfn main() {\n"
            '    let half = doubled("a", 23)\n'
            "    let mut kept: List<String> = []\n"
            "    let mut index = 0\n"
            "    while index < 400 {\n"
            '        kept = kept.push(half + "{index}")\n'
            "        index = index + 1\n"
            "    }\n"
            "    println(kept.length())\n"
            "}\n"
        )
        limit = 1_200_000 * 1024
        completed = subprocess.run(
            [sys.executable, "-m", "koschei", "run", str(path)],
            capture_output=True,
            timeout=300,
            check=False,
            cwd=REPOSITORY,
            preexec_fn=lambda: __import__("resource").setrlimit(
                __import__("resource").RLIMIT_AS, (limit, limit)
            ),
        )
        errors = completed.stderr.decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 1, errors)
        self.assertIn("KS3502", errors)
        self.assertNotIn("Traceback", errors)
        self.assertEqual(completed.stdout, b"")


if __name__ == "__main__":
    unittest.main()
