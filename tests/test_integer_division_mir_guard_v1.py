from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_native_runtime import inspect_native_mir_support
from koschei.modules import check_graph, load_graph


class IntegerDivisionMirGuardV1Tests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_dynamic_divisor_remains_unsupported(self) -> None:
        mir = self.checked_mir(
            """
fn divide(value: Int, divisor: Int) -> Int {
    return value / divisor
}

fn main() {
    println(divide(8, 2))
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertFalse(support.supported)
        self.assertTrue(
            any(
                "requires a compile-time denominator" in reason
                for reason in support.reasons
            ),
            support.reasons,
        )

    def test_literal_zero_divisor_remains_unsupported(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    println(8 / 0)
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertFalse(support.supported)
        self.assertTrue(
            any("may not be zero" in reason for reason in support.reasons),
            support.reasons,
        )


if __name__ == "__main__":
    unittest.main()
