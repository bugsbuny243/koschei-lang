from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go_mir
from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.formatter import format_source
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.parser import parse
from koschei.semantic import SemanticError


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "financial_exchange" / "typestate_settlement_v1.ks"
EXPECTED = "42\n"
GO_BINARY = shutil.which("go")


BASE = """
struct Pending {}
struct Settled {}

stateful struct Settlement<S> starts Pending {
    id: Int,
    state: S,
}

transition fn settle(item: Settlement<Pending>) -> Settlement<Settled> {
    return Settlement { id: item.id, state: Settled {} }
}
"""


class TypestateSyntaxTests(unittest.TestCase):
    def test_parser_records_stateful_and_transition_metadata(self) -> None:
        program = parse(
            BASE
            + """
fn main() {
    let item = Settlement { id: 1, state: Pending {} }
    let done = settle(item)
    println(done.id)
}
"""
        )
        settlement = next(item for item in program.structs if item.name == "Settlement")
        transition = next(item for item in program.declarations if item.name == "settle")
        self.assertTrue(getattr(settlement, "is_stateful", False))
        self.assertEqual(getattr(settlement, "initial_state", None), "Pending")
        self.assertEqual(tuple(getattr(settlement, "type_parameters", ())), ("S",))
        self.assertTrue(getattr(transition, "is_transition", False))

    def test_formatter_keeps_high_assurance_headers_together(self) -> None:
        formatted = format_source(
            """
struct Pending{}
struct Settled{}
stateful   struct Settlement<S> starts Pending{id:Int,state:S}
pure transition fn settle(item:Settlement<Pending>)->Settlement<Settled>{return Settlement{id:item.id,state:Settled{}}}
"""
        )
        self.assertIn("stateful struct Settlement<S> starts Pending", formatted)
        self.assertIn("pure transition fn settle", formatted)
        self.assertEqual(format_source(formatted), formatted)

    def test_transition_and_starts_remain_contextual_identifiers(self) -> None:
        program = parse(
            """
fn main() {
    let transition = 1
    let starts = transition + 1
    println(starts)
}
"""
        )
        self.assertEqual(program.declarations[0].name, "main")


class TypestateContractTests(unittest.TestCase):
    @staticmethod
    def _check(source: str):
        with tempfile.TemporaryDirectory(prefix="koschei-typestate-") as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    def test_valid_initial_to_settled_transition_passes(self) -> None:
        self._check(
            BASE
            + """
fn use_settled(item: Settlement<Settled>) -> Int {
    return item.id
}

fn main() {
    let pending = Settlement { id: 7, state: Pending {} }
    let done = settle(pending)
    println(use_settled(done))
}
"""
        )

    def test_non_initial_state_cannot_be_forged_in_ordinary_function(self) -> None:
        source = BASE + """
fn main() {
    let forged = Settlement { id: 7, state: Settled {} }
    println(forged.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3953"):
            self._check(source)

    def test_same_owner_cannot_transition_twice(self) -> None:
        source = BASE + """
fn main() {
    let pending = Settlement { id: 7, state: Pending {} }
    let first = settle(pending)
    let second = settle(pending)
    println(first.id)
    println(second.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_wrong_state_cannot_enter_transition(self) -> None:
        source = BASE + """
fn main() {
    let pending = Settlement { id: 7, state: Pending {} }
    let done = settle(pending)
    let illegal = settle(done)
    println(illegal.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            self._check(source)

    def test_stateful_alias_is_a_move(self) -> None:
        source = BASE + """
fn main() {
    let pending = Settlement { id: 7, state: Pending {} }
    let owner = pending
    let illegal = pending
    println(owner.id)
    println(illegal.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_stateful_binding_cannot_be_mutable(self) -> None:
        source = BASE + """
fn main() {
    let mut pending = Settlement { id: 7, state: Pending {} }
    println(pending.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3930"):
            self._check(source)

    def test_stateful_wrapper_becomes_affine_and_field_move_consumes_wrapper(self) -> None:
        source = BASE + """
struct Envelope {
    item: Settlement<Pending>
}

fn consume(item: Settlement<Pending>) {}

fn main() {
    let pending = Settlement { id: 7, state: Pending {} }
    let envelope = Envelope { item: pending }
    consume(envelope.item)
    println(envelope.item.id)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3931"):
            self._check(source)

    def test_stateful_resource_cannot_hide_in_list(self) -> None:
        source = BASE + """
fn bad(items: List<Settlement<Pending>>) -> Int {
    return items.length()
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3952"):
            self._check(source)

    def test_stateful_resource_cannot_hide_in_option(self) -> None:
        source = BASE + """
fn bad(item: Option<Settlement<Pending>>) -> Int {
    return 1
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3952"):
            self._check(source)

    def test_stateful_resource_cannot_hide_in_enum_payload(self) -> None:
        source = BASE + """
enum Boxed {
    Value(Settlement<Pending>)
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3952"):
            self._check(source)

    def test_stateful_declaration_requires_exact_state_axis(self) -> None:
        source = """
struct Pending {}

stateful struct Bad starts Pending {
    state: Pending,
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3950"):
            self._check(source)

    def test_stateful_declaration_requires_state_field(self) -> None:
        source = """
struct Pending {}

stateful struct Bad<S> starts Pending {
    payload: S,
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3950"):
            self._check(source)

    def test_initial_state_must_be_zero_field_marker(self) -> None:
        source = """
struct Pending {
    code: Int,
}

stateful struct Bad<S> starts Pending {
    state: S,
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3951"):
            self._check(source)

    def test_transition_must_keep_same_resource_family(self) -> None:
        source = """
struct Open {}
struct Closed {}

stateful struct A<S> starts Open {
    state: S,
}

stateful struct B<S> starts Open {
    state: S,
}

transition fn bad(value: A<Open>) -> B<Closed> {
    return B { state: Closed {} }
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3953"):
            self._check(source)

    def test_transition_source_cannot_escape_while_target_is_minted(self) -> None:
        source = BASE + """
fn leak(item: Settlement<Pending>) {}

transition fn bad(item: Settlement<Pending>) -> Settlement<Settled> {
    leak(item)
    return Settlement { id: item.id, state: Settled {} }
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3953"):
            self._check(source)

    def test_transition_must_return_one_direct_target_literal(self) -> None:
        source = BASE + """
transition fn bad(item: Settlement<Pending>) -> Settlement<Settled> {
    let extra = Settlement { id: item.id, state: Settled {} }
    return Settlement { id: item.id, state: Settled {} }
}

fn main() {}
"""
        with self.assertRaisesRegex(SemanticError, "KS3953"):
            self._check(source)

    def test_typestate_diagnostics_are_explainable(self) -> None:
        for code in ("KS3950", "KS3951", "KS3952", "KS3953"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))
                self.assertIsNotNone(lookup_diagnostic(code, "en"))


class TypestateRuntimeParityTests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"typestate interpreter exit: {code}")
        return output.getvalue()

    def test_public_interpreter_is_deterministic(self) -> None:
        self.assertEqual(self.interpreter_output(), EXPECTED)
        self.assertEqual(self.interpreter_output(), EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_native_build_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))

        with tempfile.TemporaryDirectory(prefix="koschei-typestate-native-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheitypestate\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "typestate-v1"
            built = subprocess.run(
                [GO_BINARY, "build", "-trimpath", "-buildvcs=false", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            executed = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(executed.stdout, EXPECTED)
            self.assertEqual(executed.stdout, self.interpreter_output())


if __name__ == "__main__":
    unittest.main()
