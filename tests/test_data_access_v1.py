"""JSON read access (`json_get`, `json_text`, ...) agrees in every executor that runs Data.

Covered: `ks run`, the checked-AST interpreter and the direct MIR runtime. The
canonical MIR executor has never run `parse_json` programs, so it is not driven
directly here.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei import runtime_budget
from koschei.cli_entry import main as cli_main
from koschei.data_access_v1 import NAMES, SIGNATURES
from koschei.diagnostics import CATALOG, ENGLISH_CATALOG
from koschei.mir import require_mir
from koschei.mir_native_runtime import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget
from koschei.semantic import SemanticError

DOCUMENT = (
    r'"\{\"name\":\"ada\",\"age\":36,\"ratio\":2.5,\"ok\":true,\"none\":null,'
    r'\"tags\":[\"a\",\"b\"],\"empty\":[],\"big\":9223372036854775808,\"neg\":-7\}"'
)

SURFACE = """
fn label(item: Data) -> String {
    return json_text(item) or "?"
}

pure fn count(data: Data) -> Int {
    return json_length(data) or 0
}

fn main() {
    let v = parse_json(DOCUMENT) or return
    println(json_kind(v))
    println(count(v))
    println(json_keys(v) or [])
    println(json_has(v, "name"))
    println(json_has(v, "missing"))
    let name = json_get(v, "name") or return
    println(json_kind(name))
    println(label(name))
    let age = json_get(v, "age") or return
    let years = json_int(age) or 0
    println(years + 1)
    println(json_float(age) or 0.0)
    let ratio = json_get(v, "ratio") or return
    println(json_float(ratio) or 0.0)
    println(json_int(ratio))
    let ok = json_get(v, "ok") or return
    println(json_bool(ok) or false)
    println(json_kind(ok))
    let none = json_get(v, "none") or return
    println(json_kind(none))
    println(json_text(none))
    let neg = json_get(v, "neg") or return
    println(json_int(neg) or 0)
    let big = json_get(v, "big") or return
    println(json_int(big))
    let tags = json_get(v, "tags") or return
    println(json_kind(tags))
    println(count(tags))
    let items = json_items(tags) or []
    for item in items {
        println(label(item))
    }
    let second = json_at(tags, 1) or return
    println(label(second))
    println(json_at(tags, 2))
    println(json_at(tags, -1))
    let empty = json_get(v, "empty") or return
    println(json_at(empty, 0))
    println(json_at(v, 0))
    println(json_get(v, "missing"))
    println(json_get(tags, "name"))
    println(json_keys(tags))
    println(json_items(v))
    println(json_length(name))
    println(json_bool(name))
    println(json_has(tags, "a"))
    println(encode_json(tags) or "?")
}
""".replace("DOCUMENT", DOCUMENT)

EXPECTED = "\n".join([
    "object",
    "9",
    '["name", "age", "ratio", "ok", "none", "tags", "empty", "big", "neg"]',
    "true",
    "false",
    "string",
    "ada",
    "37",
    "36.0",
    "2.5",
    "KS3709: json_int(): 2.5 is not an integer",
    "true",
    "bool",
    "null",
    "KS3709: json_text() expects a JSON string, found null",
    "-7",
    "KS3709: json_int(): 9223372036854775808 is outside the Int range",
    "array",
    "2",
    "a",
    "b",
    "b",
    "KS3710: json_at(): index 2 is outside 0..1",
    "KS3710: json_at(): index -1 is outside 0..1",
    "KS3710: json_at(): index 0 in an empty array",
    "KS3709: json_at() expects a JSON array, found object",
    'KS3710: json_get(): no member named "missing"',
    "KS3709: json_get() expects a JSON object, found array",
    "KS3709: json_keys() expects a JSON object, found array",
    "KS3709: json_items() expects a JSON array, found object",
    "KS3709: json_length() expects a JSON array or object, found string",
    "KS3709: json_bool() expects a JSON bool, found string",
    "false",
    '["a","b"]',
]) + "\n"


class DataAccessV1Tests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-data-access-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def check_error(self, body: str) -> str:
        source = "fn main() {\n    let v = parse_json(\"null\") or return\n" + body + "\n}\n"
        graph = load_graph(self.write(source))
        with self.assertRaises(SemanticError) as caught:
            check_graph(graph)
        return caught.exception.code

    def test_every_executor_agrees(self) -> None:
        path = self.write(SURFACE)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), EXPECTED)

        graph = load_graph(path)
        check_graph(graph)
        mir = graph.mir
        root = mir.root_module
        checked = io.StringIO()
        with redirect_stdout(checked):
            BudgetedInterpreter(
                root.program, [], namespaces=mir.namespaces(), imports=dict(root.imports),
                enums=mir.enums(), module_imports=mir.module_imports(), structs=mir.structs(),
                budget=runtime_budget.RuntimeBudget(),
            ).execute_main()
        self.assertEqual(checked.getvalue(), EXPECTED)

        sealed = require_mir(graph)
        support = inspect_native_mir_support(sealed)
        self.assertTrue(support.supported, support.reasons)
        direct = io.StringIO()
        with redirect_stdout(direct):
            self.assertEqual(run_mir_native(sealed), 0)
        self.assertEqual(direct.getvalue(), EXPECTED)

    def test_programs_with_imports_run_data_too(self) -> None:
        # A program that imports any module runs on the canonical MIR executor,
        # which used to reject parse_json with KS3101.
        path = self.write("import math\n" + SURFACE)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["run", str(path)]), 0, errors.getvalue())
        self.assertEqual(stdout.getvalue(), EXPECTED)
        graph = load_graph(path)
        check_graph(graph)
        canonical = io.StringIO()
        with redirect_stdout(canonical):
            _run_budgeted_canonical_mir(graph.mir, [], RuntimeBudget())
        self.assertEqual(canonical.getvalue(), EXPECTED)

    def test_the_checker_types_every_builtin(self) -> None:
        self.assertEqual(self.check_error('    println(json_get(v))'), "KS1301")
        self.assertEqual(self.check_error('    println(json_get(v, 1))'), "KS1301")
        self.assertEqual(self.check_error('    println(json_at(v, "0"))'), "KS1301")
        self.assertEqual(self.check_error('    println(json_text("plain"))'), "KS1301")
        self.assertEqual(self.check_error('    println(json_kind(v, v))'), "KS1301")
        # A result keeps its type: an Int from json_int cannot be added to a String.
        self.assertIn(self.check_error('    let n = json_int(v) or 0\n    println(n + "x")'), {"KS1301", "KS1306"})

    def test_data_still_cannot_be_printed(self) -> None:
        code = self.check_error('    let item = json_get(v, "a") or v\n    println(item)')
        self.assertIn(code, {"KS3608", "KS3708"})

    def test_native_builds_still_refuse_data(self) -> None:
        path = self.write(SURFACE)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["build", str(path), "-o", str(path.parent / "app")])
        self.assertNotEqual(code, 0)
        self.assertIn("KS4004", errors.getvalue())
        self.assertFalse((path.parent / "app").exists())

    def test_diagnostics_are_registered_in_both_languages(self) -> None:
        for code in ("KS3709", "KS3710"):
            self.assertIn(code, CATALOG)
            self.assertIn(code, ENGLISH_CATALOG)
        self.assertEqual(set(SIGNATURES), set(NAMES))


if __name__ == "__main__":
    unittest.main()
