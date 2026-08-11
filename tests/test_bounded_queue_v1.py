from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from koschei.bounded_queue import BoundedQueueError, BoundedQueueValue
from koschei.bounded_queue_v1 import _GO_RUNTIME
from koschei.cli import main as cli_main
from koschei.codegen_go import generate_go_mir
from koschei.diagnostics import lookup as lookup_diagnostic
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError
from koschei.type_system import INT


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "large_service" / "backpressure.ks"
EXPECTED = "true\ntrue\nfalse\n2\n2\n10\ntrue\n20\n30\n-1\n"
GO_BINARY = shutil.which("go")


class BoundedQueueCoreTests(unittest.TestCase):
    def test_capacity_is_hard_bounded(self) -> None:
        for capacity in (0, -1, 65_537):
            with self.subTest(capacity=capacity):
                with self.assertRaisesRegex(BoundedQueueError, "KS3901"):
                    BoundedQueueValue(capacity, INT)
        with self.assertRaisesRegex(BoundedQueueError, "KS3901"):
            BoundedQueueValue(True, INT)

    def test_ring_buffer_never_grows_and_preserves_fifo_wraparound(self) -> None:
        queue = BoundedQueueValue(2, INT)
        self.assertEqual(len(queue._buffer), 2)
        self.assertTrue(queue.try_send(10))
        self.assertTrue(queue.try_send(20))
        self.assertFalse(queue.try_send(30))
        self.assertEqual(len(queue._buffer), 2)
        self.assertEqual(queue.length, 2)

        ok, first = queue.try_recv()
        self.assertTrue(ok)
        self.assertEqual(first, 10)
        self.assertTrue(queue.try_send(30))
        self.assertEqual(len(queue._buffer), 2)

        self.assertEqual(queue.try_recv(), (True, 20))
        self.assertEqual(queue.try_recv(), (True, 30))
        self.assertEqual(queue.try_recv(), (False, None))
        self.assertEqual(queue.length, 0)
        self.assertEqual(len(queue._buffer), 2)

    def test_dequeue_clears_released_slot(self) -> None:
        marker = object()
        queue = BoundedQueueValue(1, INT)
        self.assertTrue(queue.try_send(marker))
        self.assertIs(queue._buffer[0], marker)
        self.assertEqual(queue.try_recv(), (True, marker))
        self.assertIsNone(queue._buffer[0])

    def test_go_runtime_uses_fixed_ring_not_append_growth(self) -> None:
        self.assertIn("make([]any, int(capacity))", _GO_RUNTIME)
        self.assertNotIn("append(queue.Buffer", _GO_RUNTIME)
        self.assertIn("queue.Count == queue.Capacity", _GO_RUNTIME)

    def test_queue_diagnostics_are_explainable(self) -> None:
        for code in ("KS3901", "KS3902", "KS3903", "KS3904"):
            with self.subTest(code=code):
                self.assertIsNotNone(lookup_diagnostic(code, "en"))
                self.assertIsNotNone(lookup_diagnostic(code, "tr"))


class BoundedQueueLanguageTests(unittest.TestCase):
    @staticmethod
    def _check(source: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            return check_graph(graph)

    @staticmethod
    def interpreter_output() -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["run", str(ENTRY)])
        if code != 0:
            raise AssertionError(f"bounded queue interpreter exit: {code}")
        return output.getvalue()

    def test_type_witness_infers_queue_item_type_across_function_boundary(self) -> None:
        self._check(
            """
fn take(q: BoundedQueue<Int>) -> Int {
    return queue_try_recv(q) or -1
}

fn main() {
    let q = bounded_queue(2, 0) or return
    queue_try_send(q, 7)
    println(take(q))
}
"""
        )

    def test_wrong_item_type_is_rejected_statically(self) -> None:
        source = """
fn main() {
    let q = bounded_queue(2, 0) or return
    queue_try_send(q, "wrong")
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS1301"):
                check_graph(graph)

    def test_capability_cannot_be_queue_item_type(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let q = bounded_queue(2, net) or return
    println(queue_len(q))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS2402"):
                check_graph(graph)

    def test_queue_generic_cannot_hide_capability_in_signature(self) -> None:
        source = """
fn bad(q: BoundedQueue<NetCaps>) -> Int {
    return queue_len(q)
}

fn main() {}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaisesRegex(SemanticError, "KS2402"):
                check_graph(graph)

    def test_public_runtime_is_deterministic_and_explicit_about_backpressure(self) -> None:
        self.assertEqual(self.interpreter_output(), EXPECTED)
        self.assertEqual(self.interpreter_output(), EXPECTED)

    @unittest.skipUnless(GO_BINARY, "Go toolchain is required for native parity")
    def test_public_native_build_matches_interpreter_byte_for_byte(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))
        self.assertIn("type KsBoundedQueue struct", generated)
        self.assertIn("queue.Count == queue.Capacity", generated)

        with tempfile.TemporaryDirectory(prefix="koschei-queue-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheiqueue\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "queue-v1"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
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
