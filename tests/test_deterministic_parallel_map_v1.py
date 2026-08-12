from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go_mir
from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "large_service" / "parallel_map.ks"
GO_BINARY = shutil.which("go")
EXPECTED = (
    "[1, 4, 9, 16, 25, 36, 49, 64]\n"
    "[1, 4, 9, 16, 25, 36, 49, 64]\n"
    "[1, 2, 3, 4, 5, 6, 7, 8]\n"
)


class DeterministicParallelMapContractTests(unittest.TestCase):
    @staticmethod
    def check_source(source: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    def test_worker_budget_is_compile_time_bounded_when_literal(self) -> None:
        source = """
fn square(value: Int) -> Int { return value * value }
fn main() {
    let out = parallel_map([1, 2], square, 0) or return
    println(out)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3920"):
            self.check_source(source)

    def test_worker_must_be_direct_named_function(self) -> None:
        source = """
fn square(value: Int) -> Int { return value * value }
fn main() {
    let worker = square
    let out = parallel_map([1, 2], worker, 2) or return
    println(out)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3921"):
            self.check_source(source)

    def test_worker_must_be_leaf_and_cannot_print(self) -> None:
        source = """
fn noisy(value: Int) -> Int {
    println(value)
    return value
}
fn main() {
    let out = parallel_map([1, 2], noisy, 2) or return
    println(out)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3922"):
            self.check_source(source)

    def test_worker_cannot_hide_nested_function_calls(self) -> None:
        source = """
fn helper(value: Int) -> Int { return value + 1 }
fn worker(value: Int) -> Int { return helper(value) }
fn main() {
    let out = parallel_map([1, 2], worker, 2) or return
    println(out)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS3922"):
            self.check_source(source)

    def test_worker_and_input_must_be_scalar_contracts(self) -> None:
        cases = (
            """
fn duplicate(value: Int) -> List<Int> { return [value, value] }
fn main() {
    let out = parallel_map([1, 2], duplicate, 2) or return
    println(out)
}
""",
            """
fn size(value: List<Int>) -> Int { return value.length() }
fn main() {
    let values = [[1], [2]]
    let out = parallel_map(values, size, 2) or return
    println(out)
}
""",
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaisesRegex(SemanticError, "KS3921"):
                    self.check_source(source)

    def test_worker_parameter_must_match_list_item(self) -> None:
        source = """
fn length(value: String) -> Int { return value.length() }
fn main() {
    let out = parallel_map([1, 2], length, 2) or return
    println(out)
}
"""
        with self.assertRaisesRegex(SemanticError, "KS1301"):
            self.check_source(source)

    def test_diagnostics_are_explainable(self) -> None:
        for code in ("KS3920", "KS3921", "KS3922", "KS3923"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "en"))
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))


class DeterministicParallelMapParityTests(unittest.TestCase):
    @staticmethod
    def interpreter_output() -> str:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"parallel_map interpreter exit {code}: {stderr.getvalue()}")
        return stdout.getvalue()

    def test_interpreter_contract_is_byte_deterministic(self) -> None:
        self.assertEqual(self.interpreter_output(), EXPECTED)
        self.assertEqual(self.interpreter_output(), EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parallel proof")
    def test_native_binary_matches_interpreter_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-parallel-map-") as workspace:
            root = Path(workspace)
            binary = root / "parallel-map"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(["build", str(ENTRY), "-o", str(binary)])
            self.assertEqual(code, 0, stderr.getvalue())
            executed = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=60, check=False
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(executed.stdout, EXPECTED)
            self.assertEqual(executed.stdout, self.interpreter_output())

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for race-detector proof")
    def test_shipping_go_runtime_is_parallel_ordered_and_race_free(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))
        self.assertIn("func ksParallelMap(", generated)
        self.assertIn("go func()", generated)
        self.assertIn("group.Add(workerCount)", generated)
        self.assertIn("make([]any, len(list))", generated)
        self.assertIn('"sync/atomic"', generated)
        self.assertIn("atomic.AddInt64(&ksDepth", generated)

        proof = r'''package main

import (
    "runtime"
    "sync/atomic"
    "testing"
)

func updatePeak(peak *int64, value int64) {
    for {
        previous := atomic.LoadInt64(peak)
        if value <= previous || atomic.CompareAndSwapInt64(peak, previous, value) {
            return
        }
    }
}

func TestParallelMapActuallyOverlapsAndPreservesOrder(t *testing.T) {
    values := make([]any, 128)
    for index := range values {
        values[index] = int64(index)
    }

    var active int64
    var peak int64
    transform := func(value any) any {
        current := atomic.AddInt64(&active, 1)
        updatePeak(&peak, current)
        for spin := 0; spin < 256; spin++ {
            runtime.Gosched()
        }
        atomic.AddInt64(&active, -1)
        return value
    }

    raw := ksParallelMap(values, transform, int64(8))
    result, ok := raw.([]any)
    if !ok {
        t.Fatalf("parallel result is %T: %v", raw, raw)
    }
    if atomic.LoadInt64(&peak) < 2 {
        t.Fatalf("parallel worker overlap was not observed; peak=%d", peak)
    }
    if len(result) != len(values) {
        t.Fatalf("result len=%d want=%d", len(result), len(values))
    }
    for index := range values {
        if result[index] != values[index] {
            t.Fatalf("result[%d]=%v want=%v", index, result[index], values[index])
        }
    }
}

func TestGeneratedKoscheiWorkerIsRaceFreeAndIndexOrdered(t *testing.T) {
    values := []any{int64(1), int64(2), int64(3), int64(4), int64(5), int64(6)}
    raw := ksParallelMap(values, ksfn_square, int64(4))
    result, ok := raw.([]any)
    if !ok {
        t.Fatalf("generated worker result is %T: %v", raw, raw)
    }
    want := []int64{1, 4, 9, 16, 25, 36}
    for index, expected := range want {
        actual, ok := result[index].(int64)
        if !ok || actual != expected {
            t.Fatalf("result[%d]=%v (%T), want=%d", index, result[index], result[index], expected)
        }
    }
    if depth := atomic.LoadInt64(&ksDepth); depth != 0 {
        t.Fatalf("call-depth guard leaked active frames: %d", depth)
    }
}
'''

        with tempfile.TemporaryDirectory(prefix="koschei-parallel-race-") as workspace:
            root = Path(workspace)
            (root / "main.go").write_text(generated, encoding="utf-8")
            (root / "parallel_map_test.go").write_text(proof, encoding="utf-8")
            (root / "go.mod").write_text(
                "module koscheiparallelmap\n\ngo 1.21\n", encoding="utf-8"
            )
            raced = subprocess.run(
                [GO_BINARY, "test", "-race", "-count=1", "."],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(raced.returncode, 0, raced.stdout + raced.stderr)
            self.assertNotIn("DATA RACE", raced.stdout + raced.stderr)


if __name__ == "__main__":
    unittest.main()
