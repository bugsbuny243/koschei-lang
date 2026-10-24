"""Native MIR-Go v2 binaries must compute what the canonical executor computes.

Every program here is checked three ways: the public ``ks run`` path, the
budgeted canonical MIR executor directly, and the binary from ``ks build``.
Standard output bytes and success/failure must agree.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import io
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli_main
from koschei.interpreter import KoscheiRuntimeError
from koschei.mir_go_native import inspect_mir_go_support
from koschei.modules import check_graph, load_graph

GO = shutil.which("go")


def _float_literal(value: float) -> str:
    # Koschei float literals have no exponent form: spell the exact value.
    text = format(Decimal(repr(value)), "f")
    return text if "." in text else text + ".0"


INT_ERRORS = """
fn main() {
    let max = 9223372036854775807
    let min = 0 - max - 1
    let zero = 0
    println(max + 1)
    println(min - 1)
    println(max * 2)
    println(-min)
    println(min / -1)
    println(min % -1)
    println(7 / zero)
    println(7 % zero)
    println("{-7 / 2} {7 / -2} {-7 % 3} {7 % -3}")
    println(3037000499 * 3037000499)
    let broken = max + 1
    let chained = broken * 2
    println("chained: {chained}")
    let caught = broken or 0
    println(caught)
}
"""

STRINGS_AND_LISTS = """
fn main() {
    let samples = ["", "çğüş", "  pad  ", "\\t\\n x \\r", "a,b,,c", "ünï ✓ 𝄞", "\u00a0nbsp\u3000"]
    for sample in samples {
        println("{sample.length()} [{sample.trim()}] {sample.contains(",")}")
        println(sample.split(","))
        let joined = "|".join(sample.split(" ")) or "?"
        println(joined)
    }
    let empty_split = "abc".split("")
    println(empty_split)
    let xs = [3, 1, 2]
    let nested = [[1, 2], [], [3]]
    println(xs.get(0))
    println(xs.get(9))
    println("{xs.push(4)} {xs} {xs.take(2)} {xs.take(-1)}")
    println("{nested} {nested.contains([3])} {xs.contains(5)} {xs.length()}")
    println("{[1, 2] < [1, 3]} {[1, 2] < [1]} {"ç" > "z"} {true < false}")
    println([Some("x"), None()])
}
"""

ENUMS_AND_OR_FORMS = """
enum Shape {
    Circle(Float),
    Square(Int),
    Label(String),
    Empty,
}

fn describe(shape: Shape) -> String {
    return match shape {
        Circle(radius) => "circle {radius * radius}",
        Square(side) => "square {side * side}",
        Label(text) => "label {text}",
        Empty => "empty",
    }
}

fn parse(flag: Bool) -> Result<Int, Error> {
    if flag {
        return Ok(42)
    }
    return Err(Error("parse failed"))
}

fn first_positive(values: List<Int>) -> Option<Int> {
    for value in values {
        if value > 0 {
            return Some(value)
        }
    }
    return None()
}

fn main() {
    let shapes = [Circle(1.5), Square(4), Label("çember"), Empty]
    for shape in shapes {
        println(describe(shape))
    }
    println(shapes)
    println(parse(true))
    println(parse(false))
    let good = parse(true) or 0
    let handled = parse(false) or {
        println("fallback")
        0 - 5
    }
    let found = first_positive([-1, 7]) or -1
    let missing = first_positive([-1]) or -1
    println("{good} {handled} {found} {missing}")
    println(Some(Some(2)))
    println("{[1].get(0) == Some(1)} {Square(3) == Square(3)} {Square(3) == Square(4)}")
}
"""

LIBRARY_TOUR = """
import text
import list

fn main() {
    println(text.ends_with("aaa", "aa"))
    println(text.strip_suffix("abab", "ab"))
    println(text.after("k=v=w", "="))
    println(text.count("banana", "an"))
    println(text.replace("a-b-c", "-", "+"))
    println(text.replace("x", "", "y"))
    println(text.lines("bir\\r\\niki\\n\\nüç\\n"))
    println(text.words("  ali\\tveli \\n deli "))
    let xs = [1, 2, 3, 4, 5]
    let none: List<Int> = []
    println(list.first(xs))
    println(list.last(xs))
    println(list.first(none))
    println("{list.reverse(xs)} {list.drop(xs, 2)} {list.concat(xs, [6])}")
    println(list.slice(xs, 1, 3))
    println(list.slice(xs, 3, 1))
    println(list.insert_at(xs, 5, 6))
    println(list.remove_at(xs, 0))
    println(list.replace_at(xs, 9, 9))
}
"""


STRUCTS = """
enum Color {
    Red,
    Green,
}

struct Inner {
    n: Int,
}

struct Record {
    label: String,
    maybe: Option<Int>,
    items: List<Inner>,
    color: Color,
    outcome: Result<Int, Error>,
    note: String or Error,
}

fn bump(record: Record) -> Int {
    let mut copy = record
    copy.maybe = Some(99)
    return copy.items.length()
}

fn main() {
    let empty = Inner { n: 0 }
    let first = Record { label: "ç x", maybe: None(), items: [Inner { n: 1 }, empty], color: Red(), outcome: Ok(3), note: "n" }
    println(first)
    let mut second = first
    second.note = Error("broken")
    second.color = Green()
    second.outcome = Err(Error("e"))
    println("{second} {first == second} {first == first}")
    println("{bump(first)} {first.maybe} {[first, second].contains(first)}")
    let holder = Some(empty)
    println("{holder} {first.items} {first.label.length()} {second.items.get(1)}")
    let mut counter = Inner { n: 0 }
    for value in [1, 2, 3] {
        counter.n = counter.n + value
    }
    println(counter.n)
}
"""

MARVEL_TOUR = """
import captain_marvel
import hela
import secure
import strange
import wanda

fn main() {
    let budget = captain_marvel.issue_budget("earth-616", ["earth-838", "earth-199999"], 2, 1) or return
    let verdict = captain_marvel.evaluate(budget, "earth-838", 0, 0) or return
    println("{budget.allowed_destinations} {verdict.allowed} {verdict.reason} {verdict.remaining_hops} {verdict.verdict_digest}")
    let blocked = captain_marvel.evaluate(budget, "earth-838", 0, 1) or return
    println("{blocked.allowed} {blocked.reason}")
    let mut forged = budget
    forged.max_effects = 9
    let refused = captain_marvel.evaluate(forged, "earth-838", 0, 1)
    println(match refused {
        Ok(v) => v.reason,
        Err(e) => "{e}",
    })

    let principal = secure.hash("principal") or return
    let reality = secure.hash("reality") or return
    let cause = secure.hash("cause") or return
    let tombstone = hela.bury(principal, "network:egress", 8, reality, cause, secure.zero_digest()) or return
    println("{tombstone.tombstone_digest} {hela.remains_dead(tombstone, principal, "network:egress", 8)} {hela.remains_dead(tombstone, principal, "network:egress", 7)}")

    let steps = [
        FutureStep { effect: "read", target: "disk", authority_before: ["net", "disk"], authority_after: ["disk"] },
        FutureStep { effect: "write", target: "disk", authority_before: ["disk"], authority_after: ["disk", "net"] },
    ]
    let path = strange.simulate(steps, 32, []) or return
    println("{path.safe} {path.first_violation} {path.reason} {path.path_digest}")

    let genesis = wanda.commit("earth-616", 0, reality, cause, secure.zero_digest()) or return
    let next = wanda.commit("earth-616", 1, reality, cause, genesis.commitment_digest) or return
    let mut rewritten = next
    rewritten.state_digest = cause
    println("{wanda.extends(genesis, next)} {wanda.extends(genesis, rewritten)} {wanda.detects_fork(next, rewritten)} {wanda.detects_rollback(next, genesis)}")
    println("{sha3_256("") or "?"} {secure.is_digest(genesis.commitment_digest)}")
}
"""


def _float_program() -> str:
    rng = random.Random(20261024)
    values = [0.0, 1.0, 0.1, 2.5, 1e15, 1e16, 1e-4, 1e-5, 5e-324, 1e300, 0.30000000000000004]
    values += [rng.uniform(-10, 10) * 10 ** rng.randint(-25, 25) for _ in range(60)]
    lines = [f"    println({_float_literal(value)})" for value in values]
    lines += [
        "    let third = 1.0 / 3.0",
        "    let zero = 0.0",
        '    println("{third} {third * 3.0} {0.1 + 0.2} {-1.5 - 2.25}")',
        "    println(1.0 / zero)",
    ]
    return "fn main() {\n" + "\n".join(lines) + "\n}\n"


@unittest.skipUnless(GO, "Go toolchain is required for native parity")
class MirGoNativeParityTests(unittest.TestCase):
    def workspace(self, files: dict[str, str]) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-mir-go-v2-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        return root

    def ks_run(self, path: Path) -> tuple[bool, str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            try:
                code = cli_main(["run", str(path)])
            except SystemExit as exit_:
                code = exit_.code
        return code == 0, stdout.getvalue()

    def canonical_run(self, path: Path) -> tuple[bool, str]:
        graph = load_graph(path)
        check_graph(graph)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            try:
                code = _run_budgeted_canonical_mir(
                    graph.mir, [], runtime_budget.RuntimeBudget()
                )
            except KoscheiRuntimeError:
                code = 1
        return code == 0, stdout.getvalue()

    def native_run(self, path: Path) -> tuple[bool, str, str]:
        binary = path.parent / "native-program"
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["build", str(path), "-o", str(binary)])
        self.assertEqual(code, 0, output.getvalue() + errors.getvalue())
        # Bytes, not text=True: universal newlines would rewrite "\r".
        completed = subprocess.run(
            [str(binary)], capture_output=True, timeout=60, check=False
        )
        return (
            completed.returncode == 0,
            completed.stdout.decode("utf-8"),
            completed.stderr.decode("utf-8", errors="replace"),
        )

    def assert_parity(self, source: str, *, extra: dict[str, str] | None = None) -> str:
        root = self.workspace({"main.ks": source, **(extra or {})})
        path = root / "main.ks"
        native_ok, native_out, native_err = self.native_run(path)
        self.assertEqual(self.canonical_run(path), (native_ok, native_out), native_err)
        self.assertEqual(self.ks_run(path), (native_ok, native_out), native_err)
        return native_out

    def test_int_overflow_and_division_errors_are_values(self) -> None:
        output = self.assert_parity(INT_ERRORS)
        self.assertIn("KS3501: Int taşması: '+'", output)
        self.assertIn("Sıfıra bölme", output)

    def test_float_rendering_matches_python_repr_rules(self) -> None:
        output = self.assert_parity(_float_program())
        self.assertIn("1000000000000000.0\n1e+16\n", output)

    def test_strings_lists_and_error_values(self) -> None:
        output = self.assert_parity(STRINGS_AND_LISTS)
        self.assertIn("String.split() ayıracı boş olamaz", output)

    def test_enums_match_and_or_forms(self) -> None:
        output = self.assert_parity(ENUMS_AND_OR_FORMS)
        self.assertIn('[Circle(1.5), Square(4), Label("çember"), Empty]', output)

    def test_core_library_compiles_natively(self) -> None:
        output = self.assert_parity(LIBRARY_TOUR)
        self.assertTrue(output.startswith('true\nSome("ab")\nSome("v=w")\n'), output)

    def test_structs_have_value_semantics_natively(self) -> None:
        output = self.assert_parity(STRUCTS)
        self.assertTrue(
            output.startswith(
                'Record { label: "ç x", maybe: None, items: [Inner { n: 1 }, Inner { n: 0 }], '
                'color: Red, outcome: Ok(3), note: "n" }\n'
            ),
            output,
        )
        self.assertIn("\n2 None true\n", output)
        self.assertTrue(output.endswith("\n6\n"), output)

    def test_structs_on_the_direct_mir_lane(self) -> None:
        # Without member calls `ks run` uses the direct MIR runtime.
        source = (
            "struct P {\n    x: Int,\n    name: String,\n}\n\n"
            "fn main() {\n    let p = P { x: 1, name: \"a\" }\n    println(p)\n"
            '    println("{[p]} {p == p} {p.x}")\n}\n'
        )
        output = self.assert_parity(source)
        self.assertEqual(output, 'P { x: 1, name: "a" }\n[P { x: 1, name: "a" }] true 1\n')

    def test_marvel_library_compiles_natively(self) -> None:
        output = self.assert_parity(MARVEL_TOUR)
        lines = output.splitlines()
        self.assertEqual(len(lines), 7, output)
        self.assertTrue(lines[0].startswith('["earth-199999", "earth-838"] true within-blast-radius 1 '))
        self.assertEqual(lines[1], "false effect-budget-exhausted")
        self.assertEqual(lines[2], "captain_marvel.evaluate: canonical budget required")
        self.assertTrue(lines[3].endswith(" true false"))
        self.assertTrue(lines[4].startswith("false Some(1) future authority expansion sha3-256:"))
        self.assertEqual(lines[5], "true false true true")
        self.assertTrue(
            lines[6].startswith("a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a ")
        )

    def test_error_inside_a_list_literal_without_variant_facts(self) -> None:
        # Member calls but no Option/Result/enum facts: `ks run` used to hand
        # this program to the checked-AST interpreter, which replaced the list
        # with the Error. Sealed MIR keeps the Error as an element everywhere.
        source = (
            "fn main() {\n    let max = 9223372036854775807\n"
            "    let values = [1, max + 1, 3]\n    println(values)\n"
            '    println(values.length())\n    println("a,b".split(","))\n}\n'
        )
        output = self.assert_parity(source)
        self.assertTrue(output.startswith("[1, KS3501:"), output)
        self.assertTrue(output.endswith(', 3]\n3\n["a", "b"]\n'), output)

    def test_local_modules_and_library_compose(self) -> None:
        helper = (
            'fn greet(name: String) -> String {\n    return "merhaba {name}"\n}\n'
        )
        source = (
            "import helper\nimport text\n\nfn main() {\n"
            '    println(helper.greet("dünya"))\n'
            '    println(text.words(" ka vor  shi "))\n}\n'
        )
        output = self.assert_parity(source, extra={"helper.ks": helper})
        self.assertEqual(output, 'merhaba dünya\n["ka", "vor", "shi"]\n')

    def test_error_valued_if_condition_skips_the_statement(self) -> None:
        # Sealed MIR guards an `if` condition with MirIsRuntimeError: an Error
        # condition runs neither arm, in every executor and natively.
        source = (
            "fn main() {\n    println(\"before\")\n    let zero = 0\n"
            "    let broken = 1 / zero\n    if broken > 0 {\n        println(\"no\")\n    }\n"
            '    println("after")\n}\n'
        )
        self.assertEqual(self.assert_parity(source), "before\nafter\n")

    def test_error_crossing_a_typed_boundary_stops_like_the_interpreter(self) -> None:
        source = (
            "fn grow(value: Int) -> Int {\n    return value * 3037000500\n}\n\n"
            'fn main() {\n    println("start")\n    println(grow(3037000500))\n}\n'
        )
        root = self.workspace({"main.ks": source})
        native = self.native_run(root / "main.ks")
        self.assertEqual(native[:2], (False, "start\n"))
        self.assertEqual(self.ks_run(root / "main.ks"), (False, "start\n"))
        self.assertIn("KS3401", native[2])

    def test_call_depth_limit_is_enforced_natively(self) -> None:
        source = (
            "fn down(n: Int) -> Int {\n    if n == 0 {\n        return 0\n    }\n"
            "    return down(n - 1)\n}\n\nfn main() {\n    println(down(500))\n"
            "    println(down(600))\n}\n"
        )
        root = self.workspace({"main.ks": source})
        ok, output, errors = self.native_run(root / "main.ks")
        self.assertEqual((ok, output), (False, "0\n"))
        self.assertIn("KS3105", errors)

    def test_unsupported_constructs_fail_closed(self) -> None:
        cases = {
            "generic struct": "struct Box<T> {\n    value: T,\n}\n\nfn main() {\n"
            "    let b = Box { value: 1 }\n    println(b.value)\n}\n",
            "callback": "fn keep(value: Int) -> Bool {\n    return value > 1\n}\n\n"
            "fn main() {\n    let kept = [1, 2].filter(keep) or []\n    println(kept)\n}\n",
            "conversion": 'fn main() {\n    let n = "12".to_int() or 0\n    println(n)\n}\n',
        }
        for name, source in cases.items():
            with self.subTest(name):
                root = self.workspace({"main.ks": source})
                graph = load_graph(root / "main.ks")
                check_graph(graph)
                self.assertFalse(inspect_mir_go_support(graph.mir).supported)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    code = cli_main(["build", str(root / "main.ks"), "-o", str(root / "bin")])
                self.assertEqual(code, 1)
                self.assertIn("KS4004", errors.getvalue())
                self.assertFalse((root / "bin").exists())

    def test_native_binary_links_no_new_host_effect_symbols(self) -> None:
        watched = (
            "syscall.Openat", "syscall.Socket", "syscall.Bind", "syscall.Listen",
            "syscall.Renameat", "syscall.Unlinkat", "os.LookupEnv", "os.Remove",
            "os.StartProcess", "io.ReadAll", "net.Dial", "net/http.NewRequest",
        )
        root = self.workspace({"main.ks": LIBRARY_TOUR})
        binary = root / "library"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli_main(["build", str(root / "main.ks"), "-o", str(binary)]), 0)
        listing = subprocess.run(
            [GO, "tool", "nm", str(binary)], capture_output=True, text=True, check=True
        ).stdout
        symbols = {line.split()[-1] for line in listing.splitlines() if line.split()}
        present = [
            name for name in watched
            if any(symbol == name or symbol.startswith(name + ".") for symbol in symbols)
        ]
        self.assertEqual(present, [])


if __name__ == "__main__":
    unittest.main()
