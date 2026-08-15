from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_native_runtime import (
    MirNativeProgramError,
    inspect_native_mir_support,
    run_mir_native,
)
from koschei.modules import check_graph, load_graph


class DataMirV1Tests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return require_mir(graph)

    def test_parse_and_encode_json_execute_from_direct_mir(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let data = parse_json("{\\"b\\":2,\\"a\\":1}") or return Error("parse failed")
    let encoded = encode_json(data) or return Error("encode failed")
    println(encoded)
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_mir_native(mir), 0)
        self.assertEqual(output.getvalue(), '{"a":1,"b":2}\n')

    def test_invalid_json_returns_replacement_error_without_ast_fallback(self) -> None:
        mir = self.checked_mir(
            """
fn main() {
    let data = parse_json("{") or return Error("invalid payload")
    let encoded = encode_json(data) or return Error("encode failed")
    println(encoded)
}
"""
        )
        support = inspect_native_mir_support(mir)
        self.assertTrue(support.supported, support.reasons)

        with self.assertRaisesRegex(MirNativeProgramError, "invalid payload"):
            run_mir_native(mir)


if __name__ == "__main__":
    unittest.main()
