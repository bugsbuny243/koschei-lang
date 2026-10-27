"""The kernel ``sha3_256`` digest and the Koschei-written ``secure`` module.

``sha3_256`` delegates to the host's audited SHA3-256 (Koschei implements no
cryptographic primitive). These tests pin it to NIST answers and ``hashlib``,
check its input bound in bytes rather than characters, keep it pure and
capability-free, and compare every Python MIR executor. ``secure`` is checked
against an independent model of its documented encoding.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import random
import tempfile
import unittest

from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.capabilities import analyze_graph
from koschei.cli_entry import main as cli_main
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph
from koschei.runtime_budget import RuntimeBudget
from koschei.secure_hash_v1 import SHA3_256_MAX_INPUT_BYTES, sha3_256_hex
from koschei.semantic import SemanticError

# FIPS 202 / NIST CSRC example values for SHA3-256.
NIST_VECTORS = {
    "": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a",
    "abc": "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532",
    "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq": (
        "41c0dba2a9d6240849100376a8235e2c82e1b9998a999e21db32dd97496d3376"
    ),
}
ALPHABET = ("a", "b", " ", "\t", "\n", "ç", "ğ", "Δ", "✓", "𝄞", "0", ":")


def literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def secure_digest(context: str, parts: list[str]) -> str:
    encoded = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        encoded += f"\n{len(part)}:{part}"
    return "sha3-256:" + hashlib.sha3_256(encoded.encode("utf-8")).hexdigest()


class SecureLibraryTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-secure-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def run_source(self, source: str) -> str:
        path = self.write(source)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(path)])
        self.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue()

    def test_known_answers_and_hashlib_agree(self) -> None:
        rng = random.Random(202)
        values = list(NIST_VECTORS) + [
            "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 40)))
            for _ in range(60)
        ]
        body = "\n".join(
            f'    println(sha3_256({literal(value)}) or "ERROR")' for value in values
        )
        output = self.run_source(f"fn main() {{\n{body}\n}}\n").splitlines()
        expected = [hashlib.sha3_256(value.encode("utf-8")).hexdigest() for value in values]
        self.assertEqual(output, expected)
        for index, value in enumerate(NIST_VECTORS):
            self.assertEqual(output[index], NIST_VECTORS[value])

    def test_input_bound_counts_utf8_bytes(self) -> None:
        self.assertEqual(SHA3_256_MAX_INPUT_BYTES, 1 << 20)
        source = """
fn doubled(seed: String, times: Int) -> String {
    let mut value = seed
    let mut index = 0
    while index < times {
        value = value + value
        index = index + 1
    }
    return value
}

fn show(value: String) {
    let digest = sha3_256(value) or "ERROR"
    println(digest)
}

fn main() {
    let ascii = doubled("a", 20)
    show(ascii)
    show(ascii + "a")
    let wide = doubled("ç", 19)
    show(wide)
    show(wide + "ç")
    // 2^20 + 2 bytes in fewer than 2^20 characters.
    show(doubled("a", 19) + doubled("ç", 18) + "ç")
}
"""
        too_large = "ERROR"
        output = self.run_source(source).splitlines()
        self.assertEqual(
            output,
            [
                hashlib.sha3_256(b"a" * (1 << 20)).hexdigest(),
                too_large,
                hashlib.sha3_256("ç".encode() * (1 << 19)).hexdigest(),
                too_large,
                too_large,
            ],
        )
        _, error = sha3_256_hex("a" * ((1 << 20) + 1))
        self.assertEqual(error, "sha3_256: input exceeds 1048576 bytes")

    def test_static_contract(self) -> None:
        cases = {
            "integer": 'let d = sha3_256(1) or ""',
            "arity": 'let d = sha3_256("a", "b") or ""',
            "missing": 'let d = sha3_256() or ""',
        }
        for name, body in cases.items():
            with self.subTest(name):
                graph = load_graph(self.write(f"fn main() {{\n    {body}\n    println(d)\n}}\n"))
                with self.assertRaises(SemanticError) as caught:
                    check_graph(graph)
                self.assertEqual(caught.exception.code, "KS1301")

    def test_digest_is_pure_and_needs_no_capability(self) -> None:
        source = (
            "import secure\n\n"
            "pure fn tag(value: String) -> String {\n"
            '    let digest = sha3_256(value) or "?"\n    return digest\n}\n\n'
            "fn main() {\n"
            '    println(tag("abc"))\n'
            '    println(secure.hash("abc") or "?")\n}\n'
        )
        path = self.write(source)
        graph = load_graph(path)
        check_graph(graph)
        self.assertFalse(analyze_graph(graph).has_any)
        abc = NIST_VECTORS["abc"]
        self.assertEqual(self.run_source(source), f"{abc}\nsha3-256:{abc}\n")

    def test_every_python_executor_agrees(self) -> None:
        source = (
            "import secure\n\nfn main() {\n"
            '    println(sha3_256("çğ✓") or "?")\n'
            '    println(secure.digest("koschei.test/v1", ["ab", "c"]) or "?")\n'
            '    println(secure.is_digest(secure.zero_digest()))\n}\n'
        )
        path = self.write(source)
        graph = load_graph(path)
        check_graph(graph)
        lanes = {}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(_run_budgeted_canonical_mir(graph.mir, [], RuntimeBudget()), 0)
        lanes["canonical"] = stdout.getvalue()
        if inspect_native_mir_support(graph.mir).supported:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                run_mir_native(graph.mir)
            lanes["direct"] = stdout.getvalue()
        lanes["ks run"] = self.run_source(source)
        expected = (
            hashlib.sha3_256("çğ✓".encode()).hexdigest()
            + "\n"
            + secure_digest("koschei.test/v1", ["ab", "c"])
            + "\ntrue\n"
        )
        for name, output in lanes.items():
            self.assertEqual(output, expected, name)

    def test_direct_mir_runtime_computes_the_same_digest(self) -> None:
        source = 'fn main() {\n    println(sha3_256("çğ✓") or "?")\n}\n'
        graph = load_graph(self.write(source))
        check_graph(graph)
        self.assertTrue(inspect_native_mir_support(graph.mir).supported)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            run_mir_native(graph.mir)
        expected = hashlib.sha3_256("çğ✓".encode()).hexdigest() + "\n"
        self.assertEqual(stdout.getvalue(), expected)
        self.assertEqual(self.run_source(source), expected)

    def test_secure_digest_encoding_and_shape(self) -> None:
        rng = random.Random(1024)
        cases = []
        for _ in range(40):
            context = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 8)))
            parts = [
                "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 6)))
                for _ in range(rng.randint(0, 4))
            ]
            cases.append((context, parts))
        # Field boundaries are length-prefixed: these must all differ.
        cases += [("ctx", ["ab", "c"]), ("ctx", ["a", "bc"]), ("ctx", ["abc"]), ("ctx", [])]
        lines = [
            f'    println(secure.digest({literal(context)}, '
            f'[{", ".join(literal(part) for part in parts)}]) or "ERROR")'
            for context, parts in cases
        ]
        lines.append('    let empty: List<String> = ["x"]')
        lines.append('    let refused = secure.digest("", empty)')
        lines.append(
            '    println(match refused {\n        Ok(_) => "accepted",\n'
            '        Err(e) => "{e}",\n    })'
        )
        lines.append('    println(secure.hash("") or "ERROR")')
        output = self.run_source(
            "import secure\n\nfn main() {\n" + "\n".join(lines) + "\n}\n"
        ).splitlines()
        expected = [secure_digest(context, parts) for context, parts in cases]
        self.assertEqual(output[: len(cases)], expected)
        self.assertEqual(len(set(expected[-4:])), 4)
        self.assertEqual(output[len(cases)], "secure.digest: context must not be empty")
        self.assertEqual(output[len(cases) + 1], "sha3-256:" + NIST_VECTORS[""])

    def test_is_digest_accepts_only_the_produced_shape(self) -> None:
        valid = "sha3-256:" + NIST_VECTORS["abc"]
        cases = {
            valid: True,
            "sha3-256:" + "0" * 64: True,
            "sha3-256:" + NIST_VECTORS["abc"].upper(): False,
            "sha3-256:" + NIST_VECTORS["abc"][:-1]: False,
            "sha3-256:" + NIST_VECTORS["abc"] + "0": False,
            "sha3-256:" + NIST_VECTORS["abc"][:-1] + "g": False,
            "sha3-512:" + NIST_VECTORS["abc"]: False,
            "sha3-256:" + NIST_VECTORS["abc"][:32] + ":" + NIST_VECTORS["abc"][33:]: False,
            NIST_VECTORS["abc"]: False,
            "": False,
            "sha3-256:": False,
        }
        lines = [f"    println(secure.is_digest({literal(value)}))" for value in cases]
        output = self.run_source(
            "import secure\n\nfn main() {\n" + "\n".join(lines) + "\n}\n"
        ).splitlines()
        self.assertEqual(output, ["true" if flag else "false" for flag in cases.values()])


if __name__ == "__main__":
    unittest.main()
