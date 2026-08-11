from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


class BoundedQueueContractGateTests(unittest.TestCase):
    @staticmethod
    def _graph(source: str):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return temporary, load_graph(path)

    def test_concrete_queue_generic_crosses_function_boundary(self) -> None:
        temporary, graph = self._graph(
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
        with temporary:
            check_graph(graph)

    def test_mismatched_queue_generic_is_still_rejected_by_typed_hir(self) -> None:
        temporary, graph = self._graph(
            """
fn take(q: BoundedQueue<Int>) -> Int {
    return queue_try_recv(q) or -1
}

fn main() {
    let q = bounded_queue(2, "") or return
    println(take(q))
}
"""
        )
        with temporary:
            with self.assertRaisesRegex(SemanticError, "KS1301"):
                check_graph(graph)

    def test_raw_queue_annotation_is_rejected_structurally(self) -> None:
        temporary, graph = self._graph(
            """
fn bad(q: BoundedQueue) -> Int {
    return queue_len(q)
}

fn main() {}
"""
        )
        with temporary:
            with self.assertRaisesRegex(SemanticError, "KS1301"):
                check_graph(graph)


if __name__ == "__main__":
    unittest.main()
