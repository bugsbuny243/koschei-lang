"""main may end the program with an Error, in every executor.

`fn main()` without a return type may `return Error(...)` or pass a failure up
with a bare `or return`: the run prints `KOSCHEI RUNTIME ERROR: <message>`
and exits 1. The direct MIR runtime and the checked-AST interpreter always
did; the canonical MIR executors and native binaries stopped with a KS3401
contract violation instead. Every other function must be able to return the
failure a bare `or return` passes up (KS1304, KS1301).
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
from koschei.interpreter import KsError
from koschei.mir_executor_v1 import execute_mir_v1
from koschei.mir_native_runtime import MirNativeProgramError
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

PROGRAMS = {
    "explicit": ('fn main() {\n    return Error("boom")\n}\n', "boom"),
    "or return": (
        'fn main() {\n    let port = "http".to_int() or return\n    println(port)\n}\n',
        "Int dönüşümü başarısız: http",
    ),
    "overflow": (
        "fn main() {\n    let big = 9223372036854775807\n    let next = big + 1 or return\n"
        "    println(next)\n}\n",
        "KS3501: Int taşması: '+' işlemi işaretli 64-bit aralığın dışına çıktı.",
    ),
}


def _write(directory: str, source: str) -> Path:
    path = Path(directory) / "main.ks"
    path.write_text(source, encoding="utf-8")
    return path


class MainErrorEdgeTests(unittest.TestCase):
    def test_every_ks_run_executor_ends_with_mains_error(self) -> None:
        for name, (source, message) in PROGRAMS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                path = _write(directory, source)
                graph = load_graph(path)
                check_graph(graph)
                mir = graph.mir
                root = mir.root_module

                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    code = _run_budgeted_canonical_mir(mir, [], runtime_budget.RuntimeBudget())
                self.assertEqual((code, stderr.getvalue()), (1, f"KOSCHEI RUNTIME ERROR: {message}\n"))

                with redirect_stdout(io.StringIO()):
                    result = execute_mir_v1(mir)
                self.assertIsInstance(result, KsError)
                self.assertEqual(result.message, message)

                with redirect_stdout(io.StringIO()), runtime_budget.host_recursion_headroom():
                    result = runtime_budget.BudgetedInterpreter(
                        root.program,
                        [],
                        namespaces=mir.namespaces(),
                        imports=dict(root.imports),
                        enums=mir.enums(),
                        module_imports=mir.module_imports(),
                        structs=mir.structs(),
                        budget=runtime_budget.RuntimeBudget(),
                    ).execute_main()
                self.assertEqual(result.message, message)

                if inspect_native_mir_support(mir).supported:
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaises(MirNativeProgramError) as raised:
                            run_mir_native(mir)
                    self.assertEqual(str(raised.exception), message)

                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    code = cli(["run", str(path)])
                self.assertEqual((code, stderr.getvalue()), (1, f"KOSCHEI RUNTIME ERROR: {message}\n"))

    @unittest.skipUnless(GO, "Go is not installed")
    def test_binaries_end_with_mains_error_like_ks_run(self) -> None:
        for name, (source, message) in PROGRAMS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                _write(directory, source)
                environment = dict(os.environ, PYTHONPATH=str(ROOT))
                build = subprocess.run(
                    [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"],
                    cwd=directory, env=environment, capture_output=True, timeout=300, check=False,
                )
                self.assertEqual(build.returncode, 0, build.stderr.decode())
                native = subprocess.run(
                    [str(Path(directory) / "app")], capture_output=True, timeout=60, check=False,
                )
                expected = f"KOSCHEI RUNTIME ERROR: {message}\n".encode()
                self.assertEqual((native.returncode, native.stdout, native.stderr), (1, b"", expected))

    def test_other_functions_must_be_able_to_return_the_failure(self) -> None:
        refused = {
            "fn parse(text: String) {\n    let port = text.to_int() or return\n    println(port)\n}\n": "KS1304",
            "fn parse(text: String) -> Int {\n    let port = text.to_int() or return\n    return port\n}\n": "KS1301",
            'fn parse(text: String) {\n    let port = text.to_int() or return Error("no")\n    println(port)\n}\n': "KS1304",
        }
        accepted = [
            "fn parse(text: String) -> Int or Error {\n    let port = text.to_int() or return\n    return port\n}\n",
            "fn parse(text: String) -> Void or Error {\n    let port = text.to_int() or return\n"
            "    println(port)\n    return\n}\n",
            "fn first(items: List<Int>) -> Option<Int> {\n    let item = items.get(0) or return\n"
            "    return Some(item)\n}\n",
        ]
        call = 'fn main() {\n    println("ok")\n}\n'
        for source, code in [*refused.items(), *((item, None) for item in accepted)]:
            with self.subTest(source), tempfile.TemporaryDirectory() as directory:
                path = _write(directory, source + call)
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    status = cli(["check", str(path)])
                if code is None:
                    self.assertEqual(status, 0, output.getvalue())
                else:
                    self.assertEqual(status, 1, output.getvalue())
                    self.assertIn(code, output.getvalue())


if __name__ == "__main__":
    unittest.main()
