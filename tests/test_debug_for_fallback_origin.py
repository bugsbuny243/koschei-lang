from __future__ import annotations

from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch

from koschei import mir_ir
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph


class ForFallbackOriginDebugTests(unittest.TestCase):
    def test_trace_synthetic_for_fallback_origin(self) -> None:
        source = """
fn main() {
    for value in [1, 2, 3, 4] {
        if value == 2 {
            continue
        }
        println(value)
        if value == 3 {
            break
        }
    }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            original_emit = mir_ir._FunctionLowerer._emit
            origins: list[str] = []

            def traced_emit(lowerer, instruction):
                if isinstance(instruction, mir_ir.MirAstFallback) and instruction.node_kind in {
                    "ForHasNext",
                    "ForBind",
                }:
                    origins.append(
                        instruction.node_kind + "\n" + "".join(traceback.format_stack(limit=12))
                    )
                return original_emit(lowerer, instruction)

            with patch.object(mir_ir._FunctionLowerer, "_emit", traced_emit):
                check_graph(graph)
            mir = require_mir(graph)
            final = [
                instruction.node_kind
                for block in mir.root_module.functions[0].blocks
                for instruction in block.instructions
                if isinstance(instruction, mir_ir.MirAstFallback)
                and instruction.node_kind in {"ForHasNext", "ForBind"}
            ]
            self.assertEqual(
                final,
                [],
                "synthetic fallbacks reached final MIR; emit origins:\n" + "\n".join(origins),
            )


if __name__ == "__main__":
    unittest.main()
