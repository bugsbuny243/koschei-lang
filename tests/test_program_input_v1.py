"""Program input (G1.2): command-line arguments and standard input.

A program reads its arguments and standard input only through
``caps.input.allow(max_bytes)``. Every executor and the MIR-Go binary must
return the same texts and the same Error values for the same input.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.capability_effect_contract_v1 import (
    INPUT_READ,
    POWER_DOMAIN_DATA,
    require_capability_method_same_power_domain,
)
from koschei.cli_entry import main as cli_main
from koschei.mir_go_native import inspect_mir_go_support
from koschei.modules import check_graph, load_graph
from koschei.program_input_v1 import MAX_INPUT_BYTES
from koschei.runtime_budget import BudgetedInterpreter, RuntimeBudget
from koschei.semantic import SemanticError

GO = shutil.which("go")

# Prints every outcome as a value: println shows an Error value's message.
REPORT = """
fn report(input: InputCaps) {
    println(input.args())
    println(input.read_text())
    println(input.read_text())
}

fn main(caps: SystemCaps) {
    report(caps.input.allow(8))
}
"""

WORDS = """
fn main(caps: SystemCaps) {
    let input = caps.input.allow(65536)
    let args = input.args() or return
    let text = input.read_text() or return
    let lines = text.split("\\n") or return
    let mut count = 0
    for line in lines {
        if line.length() > 0 {
            count = count + 1
        }
    }
    println("{args.length()} argüman: {args}")
    println("{count} dolu satır")
}
"""

# A token prints as its type: no host address and no narrowed scope.
OPAQUE = """
fn main(caps: SystemCaps) {
    let input = caps.input.allow(5)
    println("token: {input} {caps.input}")
    let home = caps.env.allow("HOME")
    println(home)
    println(caps)
}
"""
OPAQUE_OUTPUT = "token: <InputCaps> <InputRoot>\n<EnvCaps>\n<SystemCaps>\n"
OPAQUE_NATIVE = """
fn main(caps: SystemCaps) {
    let input = caps.input.allow(5)
    println("token: {input} {caps.input}")
    println(caps)
}
"""


@contextmanager
def standard_input(data: bytes | None):
    """Replace stdin for an in-process run; ``None`` is a closed descriptor."""

    stream = None if data is None else io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
    with mock.patch.object(sys, "stdin", stream):
        yield


class FailingStream:
    class buffer:  # noqa: N801 - mirrors TextIOWrapper.buffer
        @staticmethod
        def read(size: int) -> bytes:
            raise OSError(5, "Input/output error")


class ProgramInputTests(unittest.TestCase):
    def write(self, source: str, name: str = "main.ks") -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-input-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / name
        path.write_text(source, encoding="utf-8")
        return path

    def ks_run(self, path: Path, args: list[str], data: bytes | None) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with standard_input(data), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["run", str(path), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def check_error(self, source: str) -> str:
        path = self.write(source)
        graph = load_graph(path)
        with self.assertRaises(SemanticError) as caught:
            check_graph(graph)
        return caught.exception.code

    # ---- checking ----------------------------------------------------------

    def test_the_checker_bounds_and_narrows_program_input(self) -> None:
        cases = {
            "let n = 5\n    let input = caps.input.allow(n)": "KS2430",
            "let input = caps.input.allow()": "KS2430",
            'let input = caps.input.allow("5")': "KS1301",
            "let input = caps.input.allow(0)": "KS2431",
            f"let input = caps.input.allow({MAX_INPUT_BYTES + 1})": "KS2431",
            "let text = caps.input.read_text()": "KS2402",
            "let input = caps.input.allow(5)\n    let wider = input.allow(9)": "KS2403",
            'let input = caps.input.allow(5)\n    let x = input.write("x")': "KS2404",
            "let input = caps.input.allow(5)\n    let x = input.args(1)": "KS1301",
            "let input = caps.input.allow(5)\n    let xs = [input]": "KS2401",
        }
        for body, code in cases.items():
            with self.subTest(body):
                self.assertEqual(
                    self.check_error(f"fn main(caps: SystemCaps) {{\n    {body}\n}}\n"), code
                )

    def test_reading_input_is_an_effect(self) -> None:
        source = (
            "pure fn count(input: InputCaps) -> Int {\n"
            "    let args = input.args() or return 0\n    return args.length()\n}\n\n"
            "fn main(caps: SystemCaps) {\n    println(count(caps.input.allow(5)))\n}\n"
        )
        self.assertEqual(self.check_error(source), "KS3940")
        self.assertEqual(
            require_capability_method_same_power_domain("InputCaps", "read_text"),
            (INPUT_READ, POWER_DOMAIN_DATA),
        )

    def test_capabilities_are_never_compared(self) -> None:
        holder = "struct Holder {\n    input: InputCaps,\n}\n\n"
        cases = [
            "fn main(caps: SystemCaps) {\n    let a = caps.input.allow(5)\n"
            "    let same = a == a\n}\n",
            'fn main(caps: SystemCaps) {\n    let a = caps.env.allow("X")\n'
            '    let b = caps.env.allow("X")\n    let same = a != b\n}\n',
            holder + "fn main(caps: SystemCaps) {\n"
            "    let h = Holder { input: caps.input.allow(5) }\n    let same = h == h\n}\n",
        ]
        for source in cases:
            with self.subTest(source):
                self.assertEqual(self.check_error(source), "KS2407")

    def test_a_capability_renders_as_its_type_only(self) -> None:
        path = self.write(OPAQUE)
        code, output, errors = self.ks_run(path, [], b"")
        self.assertEqual(code, 0, errors)
        self.assertEqual(output, OPAQUE_OUTPUT)
        self.assertNotIn("0x", output)

    def test_the_manifest_shows_the_input_budget(self) -> None:
        path = self.write(REPORT)
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(["caps", str(path)]), 0)
        manifest = stdout.getvalue()
        self.assertIn("PROGRAM GİRDİSİ:", manifest)
        self.assertIn("stdin_bytes=8", manifest)
        self.assertIn("kullanılan işlemler: args, read_text", manifest)
        self.assertIn("DİSK: yok", manifest)

    # ---- running -----------------------------------------------------------

    def test_ks_run_hands_arguments_and_standard_input_to_the_program(self) -> None:
        path = self.write(WORDS)
        code, output, errors = self.ks_run(
            path, ["bir", "iki üç", "--", "-x", "--max-steps"], "a\n\nb\nç\n".encode()
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(
            output, '4 argüman: ["bir", "iki üç", "-x", "--max-steps"]\n3 dolu satır\n'
        )

    def test_outcomes_are_values(self) -> None:
        path = self.write(REPORT)
        cases = [
            ([], b"", "[]\n\n\n"),
            (["a"], b"12345678", '["a"]\n12345678\n\n'),
            ([], b"123456789", "[]\nKS3431: Standart girdi bütçesi aşıldı: en fazla 8 bayt okunabilir.\n\n"),
            ([], b"1234567890", "[]\nKS3431: Standart girdi bütçesi aşıldı: en fazla 8 bayt okunabilir.\n0\n"),
            ([], b"\xff\xfe", "[]\nKS3430: Standart girdi geçerli UTF-8 metin değil.\n\n"),
            (["ok", "\udcff"], b"", "KS3430: 2. program argümanı geçerli UTF-8 metin değil.\n\n\n"),
            ([], None, "[]\n\n\n"),
        ]
        for args, data, expected in cases:
            with self.subTest(args=args, data=data):
                code, output, errors = self.ks_run(path, args, data)
                self.assertEqual(code, 0, errors)
                self.assertEqual(output, expected)

    def test_a_failing_read_is_an_error_value(self) -> None:
        path = self.write(REPORT)
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", FailingStream()),
            redirect_stdout(stdout),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli_main(["run", str(path)]), 0)
        self.assertEqual(
            stdout.getvalue(),
            "[]\nKS3432: Standart girdi okunamadı.\nKS3432: Standart girdi okunamadı.\n",
        )

    def test_every_executor_agrees(self) -> None:
        path = self.write(WORDS)
        graph = load_graph(path)
        check_graph(graph)
        mir = graph.mir
        root = mir.root_module
        args = ["x", "y"]
        data = "bir\niki\n".encode()

        checked = io.StringIO()
        with standard_input(data), redirect_stdout(checked):
            BudgetedInterpreter(
                root.program,
                args,
                namespaces=mir.namespaces(),
                imports=dict(root.imports),
                enums=mir.enums(),
                module_imports=mir.module_imports(),
                structs=mir.structs(),
                budget=runtime_budget.RuntimeBudget(),
            ).execute_main()

        canonical = io.StringIO()
        with standard_input(data), redirect_stdout(canonical):
            _run_budgeted_canonical_mir(mir, args, RuntimeBudget())

        code, public, errors = self.ks_run(path, args, data)
        self.assertEqual(code, 0, errors)
        expected = '2 argüman: ["x", "y"]\n2 dolu satır\n'
        self.assertEqual(checked.getvalue(), expected)
        self.assertEqual(canonical.getvalue(), expected)
        self.assertEqual(public, expected)

    def test_arguments_do_not_leak_between_runs(self) -> None:
        path = self.write(REPORT)
        self.assertEqual(self.ks_run(path, ["first"], b"")[1], '["first"]\n\n\n')
        self.assertEqual(self.ks_run(path, [], b"")[1], "[]\n\n\n")

    # ---- native ------------------------------------------------------------

    def build(self, path: Path) -> Path:
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        return binary

    @staticmethod
    def native(binary: Path, args: list[str], data: bytes | None):
        command = [str(binary), *(os.fsencode(item) for item in args)]
        if data is None:
            # Start the binary with descriptor 0 closed.
            return subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                preexec_fn=lambda: os.close(0),
                capture_output=True,
                timeout=60,
                check=False,
            )
        return subprocess.run(command, input=data, capture_output=True, timeout=60, check=False)

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_the_native_binary_matches_ks_run(self) -> None:
        path = self.write(REPORT)
        binary = self.build(path)
        cases = [
            ([], b""),
            (["a", "b c", "ğüşiöç"], b"12345678"),
            ([], b"123456789"),
            ([], b"1234567890"),
            ([], b"\xe2\x82"),
            ([], "﻿çok".encode()),
            ([], b"ab\xed\xa0\x80"),  # an encoded surrogate is not UTF-8
            (["ok", "\udcff"], b""),
            ([], None),
        ]
        for args, data in cases:
            with self.subTest(args=args, data=data):
                code, expected, errors = self.ks_run(path, args, data)
                self.assertEqual(code, 0, errors)
                completed = self.native(binary, args, data)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.decode("utf-8"), expected)

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_native_tokens_render_the_same(self) -> None:
        path = self.write(OPAQUE_NATIVE)
        binary = self.build(path)
        expected = "token: <InputCaps> <InputRoot>\n<SystemCaps>\n"
        self.assertEqual(self.ks_run(path, [], b"")[1], expected)
        completed = self.native(binary, [], b"")
        self.assertEqual(completed.stdout.decode("utf-8"), expected)

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_a_native_read_failure_is_the_same_error_value(self) -> None:
        path = self.write(REPORT)
        binary = self.build(path)
        # Reading a directory fails in the kernel (EISDIR).
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            completed = subprocess.run(
                [str(binary)], stdin=directory, capture_output=True, timeout=60, check=False
            )
        finally:
            os.close(directory)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.decode("utf-8"),
            "[]\nKS3432: Standart girdi okunamadı.\nKS3432: Standart girdi okunamadı.\n",
        )

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_a_large_input_streams_through_the_budget(self) -> None:
        source = (
            "fn main(caps: SystemCaps) {\n    let input = caps.input.allow(1048576)\n"
            "    let text = input.read_text() or return\n    println(text.length())\n}\n"
        )
        path = self.write(source)
        binary = self.build(path)
        for size, expected in ((1048576, "1048576\n"), (1048577, "")):
            with self.subTest(size=size):
                data = b"k" * size
                self.assertEqual(self.ks_run(path, [], data)[1], expected)
                completed = self.native(binary, [], data)
                self.assertEqual(completed.stdout.decode("utf-8"), expected)

    def test_other_authority_stays_closed_natively(self) -> None:
        cases = {
            # Read-only disk and env go through the native broker now
            # (tests/test_native_broker_v1.py); writing and the network do not.
            "env": 'fn main(caps: SystemCaps) {\n    let net = caps.net.allow("https://example.com")\n'
            '    println(net.get("https://example.com/") or "")\n}\n',
            "disk": 'fn main(caps: SystemCaps) {\n    let d = caps.disk.allow("/tmp")\n'
            '    println(d.read("/tmp/x") or "")\n}\n',
            "struct field": "struct Holder {\n    input: InputCaps,\n}\n\n"
            "fn main(caps: SystemCaps) {\n    let h = Holder { input: caps.input.allow(5) }\n"
            "    let args = h.input.args() or return\n    println(args)\n}\n",
            "two parameters": "fn main(caps: SystemCaps, other: SystemCaps) {\n    println(1)\n}\n",
        }
        for name, source in cases.items():
            with self.subTest(name):
                path = self.write(source)
                graph = load_graph(path)
                try:
                    check_graph(graph)
                except SemanticError:
                    continue
                support = inspect_mir_go_support(graph.mir)
                self.assertFalse(support.supported)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    code = cli_main(["build", str(path), "-o", str(path.parent / "bin")])
                self.assertEqual(code, 1)
                self.assertIn("KS4004", errors.getvalue())
                self.assertFalse((path.parent / "bin").exists())
        env_graph = load_graph(self.write(cases["env"]))
        check_graph(env_graph)
        self.assertTrue(
            any("(G2)" in reason for reason in inspect_mir_go_support(env_graph.mir).reasons)
        )

    @unittest.skipIf(GO is None, "Go toolchain is not installed")
    def test_the_input_binary_links_no_resource_access(self) -> None:
        binary = self.build(self.write(WORDS))
        listing = subprocess.run(
            [GO, "tool", "nm", str(binary)], capture_output=True, text=True, check=True
        ).stdout
        symbols = {line.split()[-1] for line in listing.splitlines() if line.split()}
        watched = (
            "syscall.Socket", "syscall.Bind", "syscall.Listen", "syscall.Renameat",
            "syscall.Unlinkat", "os.LookupEnv", "os.Getenv", "os.Remove", "os.OpenFile",
            "os.StartProcess", "io.ReadAll", "net.Dial", "net/http.NewRequest",
        )
        present = [
            name for name in watched
            if any(symbol == name or symbol.startswith(name + ".") for symbol in symbols)
        ]
        self.assertEqual(present, [])

    def test_programs_without_input_keep_a_zero_parameter_native_main(self) -> None:
        path = self.write('fn main() {\n    println("hi")\n}\n')
        graph = load_graph(path)
        check_graph(graph)
        from koschei.mir_go_native import generate_go_mir_native

        source = generate_go_mir_native(graph.mir)
        self.assertNotIn("_ksInputReadText", source)
        self.assertNotIn('"io"', source)


if __name__ == "__main__":
    unittest.main()
