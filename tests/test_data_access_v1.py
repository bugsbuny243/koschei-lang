"""Reading JSON Data and quoting JSON text (data_access_v1).

The methods, json_quote and the public KS370x codes must give the same bytes
in the checked-AST interpreter, the canonical MIR executor, `ks run` and
native binaries; a native build of a JSON program used to be refused.
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
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli
from koschei.data_access_v1 import data_method, json_quote, public_message
from koschei.data_json_v1 import decode, encode, quote
from koschei.data_language_v1 import DataValue
from koschei.interpreter import KsError
from koschei.mir_native_runtime import MirNativeProgramError
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph
from koschei.value_budget_v1 import STRING_MESSAGE

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

PROGRAM = r'''
fn total(items: Data) -> Int or Error {
    let count = items.length() or return
    let mut index = 0
    let mut sum = 0
    while index < count {
        let item = items.at(index) or return
        let qty = item.get("qty") or return
        let value = qty.int() or return
        sum = sum + value
        index = index + 1
    }
    return sum
}

fn describe(source: String) -> String {
    let data = parse_json(source) or {
        return "parse error"
    }
    let kind = data.kind()
    if kind == "object" {
        let keys = data.keys() or return "no keys"
        return "object {keys}"
    }
    if kind == "number" {
        let number = data.number() or return "?"
        let whole = data.int() or -1
        return "number {number} {whole}"
    }
    return kind
}

fn main() {
    let order = parse_json("\{\"id\": 42, \"customer\": \"Ayşe \\\"A\\\"\", \"total\": 129.90, \"paid\": true, \"note\": null, \"items\": [\{\"sku\": \"k-1\", \"qty\": 2\}, \{\"sku\": \"k-2\", \"qty\": 1\}]\}") or return
    println(order.kind())
    println(order.keys())
    let id = order.get("id") or return
    println(id.int())
    let customer = order.get("customer") or return
    println(customer.text())
    let price = order.get("total") or return
    println(price.number())
    println(price.int())
    let paid = order.get("paid") or return
    println(paid.bool())
    let note = order.get("note") or return
    println(note.is_null())
    println(note.text())
    println(order.get("missing"))
    let items = order.get("items") or return
    println(items.length())
    println(total(items))
    println(items.at(2))
    println(id.length())
    let bad = parse_json("[\{\"qty\": 2.5\}]") or return
    println(total(bad))
    let a = parse_json("\{\"x\": [1, 2.0, \"ğ\"], \"y\": null\}") or return
    let b = parse_json("\{\"y\":null,\"x\":[1,2,\"ğ\"]\}") or return
    let c = parse_json("\{\"y\":false,\"x\":[1,2,\"ğ\"]\}") or return
    println(a == b)
    println(a == c)
    println([a, b])
    for source in ["\{\"ö\": 1, \"z\": 2, \"a\": 3, \"Z\": 4, \"é\": 5\}", "123456789012345678901234567890", "9223372036854775807", "-9223372036854775808", "9223372036854775808", "1e2", "-0.0", "1.5e-10", "\"x\"", "[]", "\{\}", "true", "null", "[1,"] {
        println(describe(source))
    }
    let quoted = json_quote("Ayşe \"A\"\n\t\\ 😀") or return
    println(quoted)
    let reply = "\{\"customer\": {quoted}, \"count\": {items.length() or 0}\}"
    let again = parse_json(reply) or return
    println(encode_json(again))
}
'''

EXPECTED = '''object
["customer", "id", "items", "note", "paid", "total"]
42
Ayşe "A"
129.9
KS3709: JSON sayısı Int değil: 129.9
true
true
KS3709: JSON değeri string değil: null
KS3709: JSON nesnesinde "missing" anahtarı yok
2
3
KS3709: JSON dizisinde 2 indeksi yok (uzunluk 2)
KS3709: JSON değeri array ya da object değil: number
KS3709: JSON sayısı Int değil: 2.5
true
false
[<data>, <data>]
object ["Z", "a", "z", "é", "ö"]
number 1.2345678901234567890123456789e29 -1
number 9223372036854775807 9223372036854775807
number -9223372036854775808 -9223372036854775808
number 9223372036854775808 -1
number 100 100
number 0 0
number 1.5e-10 -1
string
array
object []
bool
null
parse error
"Ayşe \\"A\\"\\n\\t\\\\ 😀"
{"count":2,"customer":"Ayşe \\"A\\"\\n\\t\\\\ 😀"}
'''

FAILURES = {
    '"[1, 2"': "KS3705 [byte 5]: unterminated JSON array",
    '"\\{\\"a\\": 1, \\"a\\": 2\\}"': 'KS3704 [byte 9]: duplicate JSON object key "a"',
    '"[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]"': (
        "KS3702 [byte 64]: JSON depth exceeds limit 64"
    ),
}


def _write(directory: str, source: str) -> Path:
    path = Path(directory) / "main.ks"
    path.write_text(source, encoding="utf-8")
    return path


def _failing(source: str) -> str:
    return f"fn main() {{\n    let data = parse_json({source}) or return\n    println(encode_json(data) or \"\")\n}}\n"


class DataOperationTests(unittest.TestCase):
    def test_methods_read_every_kind_and_refuse_the_wrong_one(self) -> None:
        value = DataValue(decode('{"s": "x", "n": 7, "f": 0.5, "b": false, "z": null, "a": [1], "o": {}}'))
        member = lambda key: data_method(value, "get", [key])  # noqa: E731
        self.assertEqual([data_method(member(key), "kind", []) for key in "snfbzao"],
                         ["string", "number", "number", "bool", "null", "array", "object"])
        self.assertEqual(data_method(member("s"), "text", []), "x")
        self.assertEqual(data_method(member("n"), "int", []), 7)
        self.assertEqual(data_method(member("f"), "number", []), "0.5")
        self.assertIs(data_method(member("b"), "bool", []), False)
        self.assertIs(data_method(member("z"), "is_null", []), True)
        self.assertEqual(data_method(member("a"), "length", []), 1)
        self.assertEqual(data_method(value, "keys", []), sorted("snfbzao"))
        for target, method, arguments in (
            ("s", "int", []), ("n", "text", []), ("z", "bool", []), ("s", "length", []),
            ("a", "get", ["k"]), ("o", "at", [0]), ("a", "at", [1]), ("a", "at", [-1]),
            ("f", "int", []), ("n", "keys", []),
        ):
            with self.subTest(target=target, method=method):
                result = data_method(member(target), method, arguments)
                self.assertIsInstance(result, KsError)
                self.assertTrue(result.message.startswith("KS3709: "), result.message)

    def test_quote_escapes_like_the_encoder(self) -> None:
        for text in ("", "plain", 'a"b\\c', "\b\f\n\r\t\x00\x1f\x7f", "ğ 😀  "):
            with self.subTest(text=text):
                self.assertEqual(quote(text), encode(text))
                self.assertEqual(decode(json_quote(text)), text)
        self.assertEqual(json_quote("\x01" * (1 << 22)).message, STRING_MESSAGE)
        self.assertEqual(public_message("KS3605 [byte 1]: x"), "KS3705 [byte 1]: x")
        self.assertEqual(public_message("KS3709: x"), "KS3709: x")

    def test_the_checker_types_data_methods_and_json_quote(self) -> None:
        head = 'fn main() {\n    let data = parse_json("[1]") or return\n'
        refused = {
            '    println(data.get(1))\n': "KS1301",
            '    println(data.at("0"))\n': "KS1301",
            '    println(data.kind(1))\n': "KS1301",
            '    println(data.values())\n': "KS1502",
            '    println(json_quote(1))\n': "KS1301",
            '    println(json_quote())\n': "KS1301",
            '    println(data)\n': "KS3708",
        }
        for line, code in refused.items():
            with self.subTest(line=line.strip()), tempfile.TemporaryDirectory() as directory:
                path = _write(directory, head + line + "}\n")
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli(["check", str(path)]), 1, output.getvalue())
                self.assertIn(code, output.getvalue())


class DataExecutorTests(unittest.TestCase):
    def outputs(self, source: str) -> dict[str, str]:
        results: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, source)
            graph = load_graph(path)
            check_graph(graph)
            mir = graph.mir
            root = mir.root_module
            runs = {
                "ks run": lambda: cli(["run", str(path)]),
                "canonical": lambda: _run_budgeted_canonical_mir(mir, [], runtime_budget.RuntimeBudget()),
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
            for name, run in runs.items():
                stdout = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                    with runtime_budget.host_recursion_headroom():
                        run()
                results[name] = stdout.getvalue()
        return results

    def test_every_ks_run_executor_reads_the_same(self) -> None:
        for name, output in self.outputs(PROGRAM).items():
            with self.subTest(executor=name):
                self.assertEqual(output, EXPECTED)

    def test_the_direct_mir_runtime_quotes_and_codes_alike(self) -> None:
        source = (
            'fn main() {\n    let quoted = json_quote("a\\"b\\n") or return\n    println(quoted)\n'
            '    let data = parse_json("[1,") or return\n}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            graph = load_graph(_write(directory, source))
            check_graph(graph)
            self.assertTrue(inspect_native_mir_support(graph.mir).supported)
            stdout = io.StringIO()
            with redirect_stdout(stdout), self.assertRaises(MirNativeProgramError) as raised:
                run_mir_native(graph.mir)
        self.assertEqual(stdout.getvalue(), '"a\\"b\\n"\n')
        self.assertEqual(str(raised.exception), "KS3705 [byte 3]: unexpected end of JSON input")

    def test_codec_failures_carry_the_public_codes(self) -> None:
        for source, message in FAILURES.items():
            with self.subTest(message), tempfile.TemporaryDirectory() as directory:
                path = _write(directory, _failing(source))
                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    self.assertEqual(cli(["run", str(path)]), 1)
                self.assertEqual(stderr.getvalue(), f"KOSCHEI RUNTIME ERROR: {message}\n")

    @unittest.skipUnless(GO, "Go is not installed")
    def test_binaries_read_and_fail_like_ks_run(self) -> None:
        cases = [(PROGRAM, 0, EXPECTED, "")] + [
            (_failing(source), 1, "", f"KOSCHEI RUNTIME ERROR: {message}\n")
            for source, message in FAILURES.items()
        ]
        for source, code, stdout, stderr in cases:
            with self.subTest(stderr or "program"), tempfile.TemporaryDirectory() as directory:
                _write(directory, source)
                build = subprocess.run(
                    [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"],
                    cwd=directory, env=dict(os.environ, PYTHONPATH=str(ROOT)),
                    capture_output=True, timeout=300, check=False,
                )
                self.assertEqual(build.returncode, 0, build.stderr.decode())
                native = subprocess.run(
                    [str(Path(directory) / "app")], capture_output=True, timeout=60, check=False,
                )
                self.assertEqual(
                    (native.returncode, native.stdout.decode(), native.stderr.decode()),
                    (code, stdout, stderr),
                )


if __name__ == "__main__":
    unittest.main()
