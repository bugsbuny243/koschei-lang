from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.cli import main
from koschei.interpreter import Interpreter, KoscheiRuntimeError, SystemCaps
from koschei.modules import check_graph, load_graph
from koschei.parser import parse


GO = shutil.which("go")


class RuntimeTypeContractTests(unittest.TestCase):
    def test_typed_list_and_map_contracts_run_after_check(self) -> None:
        source_text = """
fn names() -> List<String> {
    return ["Ada", "Lin"]
}

fn count(config: Map<String, Int>) -> Int {
    return config.get("count") or 0
}

fn first(values: List<String>) -> String {
    return values.get(0) or "none"
}

fn main() {
    let people = names()
    let config = {"count": 2}
    println(first(people))
    println(count(config))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(source_text, encoding="utf-8")
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "Ada\n2\n")

    def test_nested_typed_collections_run(self) -> None:
        source_text = """
fn first_port(rows: List<Map<String, Int>>) -> Int {
    let fallback = {"port": 0}
    let row = rows.get(0) or fallback
    return row.get("port") or 0
}

fn main() {
    println(first_port([{"port": 8080}]))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(source_text, encoding="utf-8")
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "8080\n")

    def test_ordinary_runtime_mismatch_is_not_reported_as_capability_attack(self) -> None:
        program = parse(
            """
fn consume(values: List<Int>) {
    println(values.length())
}
"""
        )
        interpreter = Interpreter(program, [])
        with self.assertRaises(KoscheiRuntimeError) as raised:
            interpreter._call_function(program.declarations[0], [["wrong"]])
        self.assertEqual(raised.exception.code, "KS3106")
        self.assertIn("capability ihlali değildir", raised.exception.message)
        self.assertNotIn("type-laundering", raised.exception.message)

    def test_capability_mismatch_keeps_security_classification(self) -> None:
        program = parse(
            """
fn consume(value: String) {
    println(value)
}
"""
        )
        interpreter = Interpreter(program, [])
        token = SystemCaps().net.allow("https://example.com")
        with self.assertRaises(KoscheiRuntimeError) as raised:
            interpreter._call_function(program.declarations[0], [token])
        self.assertEqual(raised.exception.code, "KS3401")
        self.assertIn("capability", raised.exception.message)


class DivisionContractTests(unittest.TestCase):
    SOURCE = """
fn percent(total: Int) -> Int {
    return total * 20 / 100
}

fn truncate_negative() -> Int {
    return -5 / 2
}

fn half(value: Float) -> Float {
    return value / 2.0
}

fn main() {
    println(percent(125))
    println(truncate_negative())
    println(half(5.0))
}
"""

    def test_interpreter_matches_static_numeric_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(self.SOURCE, encoding="utf-8")
            check_graph(load_graph(source))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "25\n-2\n2.5\n")

    @unittest.skipUnless(GO, "Go toolchain is required")
    def test_native_division_matches_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "main.ks"
            binary = root / "program"
            source.write_text(self.SOURCE, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["build", str(source), "-o", str(binary)])
            self.assertEqual(code, 0)
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=True
            )
        self.assertEqual(run.stdout, "25\n-2\n2.5\n")

    def test_int_min_div_minus_one_reports_overflow(self) -> None:
        source_text = """
fn overflow() -> Int or Error {
    return -9223372036854775808 / -1
}

fn main() {
    let value = overflow() or 0
    println(value)
}
"""
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "main.ks"
            source.write_text(source_text, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["run", str(source)])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "0\n")


if __name__ == "__main__":
    unittest.main()
