from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from koschei.cli import main
from koschei.codegen_go import generate_go, generate_go_mir
from koschei.interpreter import run_mir
from koschei.mir import MirGraph, MirIntegrityError, require_mir, to_dict
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


class MirLoweringTests(unittest.TestCase):
    def checked_graph(self, path: Path):
        graph = load_graph(path)
        check_graph(graph)
        return graph

    def test_checked_graph_attaches_sealed_mir(self) -> None:
        graph = self.checked_graph(EXAMPLES / "hello.ks")
        mir = require_mir(graph)

        self.assertIsInstance(mir, MirGraph)
        self.assertEqual(mir.version, 3)
        self.assertRegex(mir.fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(mir.root_module.name, "hello")
        mir.assert_sealed()

    def test_fingerprint_changes_when_same_typed_body_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text('fn main() { println(41) }\n', encoding="utf-8")
            first = require_mir(self.checked_graph(path)).fingerprint
            path.write_text('fn main() { println(42) }\n', encoding="utf-8")
            second = require_mir(self.checked_graph(path)).fingerprint

        self.assertNotEqual(first, second)

    def test_fingerprint_is_deterministic_across_directories(self) -> None:
        source = (EXAMPLES / "hello.ks").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first) / "hello.ks"
            second_path = Path(second) / "hello.ks"
            first_path.write_text(source, encoding="utf-8")
            second_path.write_text(source, encoding="utf-8")

            first_mir = require_mir(self.checked_graph(first_path))
            second_mir = require_mir(self.checked_graph(second_path))

        self.assertEqual(first_mir.fingerprint, second_mir.fingerprint)

    def test_mir_preserves_typed_expression_lookup(self) -> None:
        mir = require_mir(self.checked_graph(EXAMPLES / "hello.ks"))
        typed = mir.root_module.typed_report.expressions[0]

        self.assertEqual(mir.root_module.type_of(typed.expression), typed.type)

    def test_multi_module_dependency_order_is_stable(self) -> None:
        mir = require_mir(self.checked_graph(EXAMPLES / "app.ks"))
        names = [module.name for module in mir.in_dependency_order()]

        self.assertEqual(names[-1], "app")
        self.assertEqual(len(names), len(set(names)))
        self.assertGreater(len(names), 1)

    def test_generic_aggregate_contracts_are_visible_in_mir_json(self) -> None:
        source = """
struct Box<T> {
    value: T,
}

enum Maybe<T> {
    Present(T),
    Missing,
}

fn main() {
    let box = Box { value: 7 }
    let item = Present("Ada")
    println(box.value)
    println(match item { Present(value) => value, Missing => "none" })
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            payload = to_dict(require_mir(self.checked_graph(path)))

        module = payload["modules"][0]
        self.assertEqual(
            module["structs"], [{"name": "Box", "type_parameters": ["T"]}]
        )
        self.assertEqual(
            module["enums"], [{"name": "Maybe", "type_parameters": ["T"]}]
        )


class MirIntegrityTests(unittest.TestCase):
    def test_unchecked_graph_is_rejected_before_backend(self) -> None:
        graph = load_graph(EXAMPLES / "hello.ks")

        with self.assertRaises(MirIntegrityError) as caught:
            require_mir(graph)

        self.assertEqual(caught.exception.code, "KS5002")

    def test_mutated_mir_contract_breaks_the_seal(self) -> None:
        graph = load_graph(EXAMPLES / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        root = mir.root_module
        forged_modules = dict(mir.modules)
        forged_modules[mir.root] = replace(root, name="tampered")
        forged = replace(mir, modules=forged_modules)

        with self.assertRaises(MirIntegrityError) as caught:
            forged.assert_sealed()

        self.assertEqual(caught.exception.code, "KS5002")

    def test_mir_maps_are_read_only(self) -> None:
        graph = load_graph(EXAMPLES / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)

        with self.assertRaises(TypeError):
            mir.modules[mir.root] = mir.root_module
        with self.assertRaises(TypeError):
            mir.root_module.imports["fake"] = mir.root

    def test_failed_recheck_clears_previous_mir(self) -> None:
        graph = load_graph(EXAMPLES / "hello.ks")
        check_graph(graph)
        self.assertIsNotNone(graph.mir)
        function = graph.root_module.program.declarations[0]
        statements = list(function.body.statements)
        call_statement = statements[2]
        statements[2] = replace(
            call_statement,
            expression=replace(
                call_statement.expression,
                arguments=(replace(
                    call_statement.expression.arguments[0],
                    name="missing_value",
                ),),
            ),
        )
        broken = replace(
            function,
            body=replace(function.body, statements=tuple(statements)),
        )
        graph.root_module.program = replace(
            graph.root_module.program, declarations=(broken,)
        )

        with self.assertRaises(SemanticError):
            check_graph(graph)

        self.assertIsNone(graph.mir)

    def test_capability_failure_never_reaches_mir(self) -> None:
        graph = load_graph(EXAMPLES / "supply_chain" / "main.ks")

        with self.assertRaises(SemanticError):
            check_graph(graph)

        self.assertIsNone(graph.mir)


class MirBackendTests(unittest.TestCase):
    def checked_mir(self, path: Path) -> MirGraph:
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_interpreter_executes_sealed_mir(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_mir(self.checked_mir(EXAMPLES / "hello.ks"))

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "Koschei\n1\n")

    def test_native_adapter_matches_existing_checked_codegen(self) -> None:
        graph = load_graph(EXAMPLES / "app.ks")
        check_graph(graph)
        mir = require_mir(graph)

        self.assertEqual(
            generate_go_mir(mir),
            generate_go(graph.root_module.program, graph),
        )


class MirCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = main(argv)
            except SystemExit as exit_signal:
                code = int(exit_signal.code or 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_exposes_mir_command(self) -> None:
        code, output, _ = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("mir", output)
        self.assertIn("backend-independent MIR", output)

    def test_mir_command_emits_machine_readable_contract(self) -> None:
        code, output, error = self.run_cli(["mir", str(EXAMPLES / "hello.ks")])

        self.assertEqual(code, 0, error)
        payload = json.loads(output)
        self.assertEqual(payload["version"], 3)
        self.assertEqual(payload["root"], "hello")
        self.assertRegex(payload["fingerprint"], r"^[0-9a-f]{64}$")

    def test_check_json_includes_mir_identity(self) -> None:
        code, output, error = self.run_cli(
            ["check", "--json", str(EXAMPLES / "hello.ks")]
        )

        self.assertEqual(code, 0, error)
        payload = json.loads(output)
        self.assertEqual(payload["mir_version"], 3)
        self.assertRegex(payload["mir_fingerprint"], r"^[0-9a-f]{64}$")

    def test_explain_knows_mir_integrity_diagnostic(self) -> None:
        code, output, error = self.run_cli(["--lang", "en", "explain", "KS5002"])

        self.assertEqual(code, 0, error)
        self.assertIn("Invalid MIR integrity seal", output)


if __name__ == "__main__":
    unittest.main()
