from pathlib import Path
import tempfile
import unittest

from koschei.modules import check_graph, load_graph
from koschei.native_sigil_semantics_v1 import NativeSigilSemanticError
from koschei.parser import parse


class NativeSigilGraphIntegrationTests(unittest.TestCase):
    def _graph(self, source: str):
        directory = tempfile.TemporaryDirectory(prefix="koschei-native-graph-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        return load_graph(path)

    def test_check_graph_attaches_native_sigil_mir(self) -> None:
        graph = self._graph(
            "ka treasury;\n"
            "vor withdrawal;\n"
            "shi evidence;\n"
            "thal recovery;\n"
            "nur visibility;\n"
            "fn main() { return }\n"
        )
        check_graph(graph)
        self.assertIsNotNone(graph.mir)
        self.assertIn(graph.root, graph.native_sigil_mir)
        native = graph.native_sigil_mir[graph.root]
        native.assert_sealed()
        self.assertEqual(
            tuple(binding.sigil for binding in native.bindings),
            ("ka", "vor", "shi", "thal", "nur"),
        )

    def test_graph_without_native_sigils_has_no_native_mir(self) -> None:
        graph = self._graph("fn main() { return }\n")
        check_graph(graph)
        self.assertIsNotNone(graph.mir)
        self.assertEqual(graph.native_sigil_mir, {})

    def test_failed_recheck_clears_both_compiler_products(self) -> None:
        graph = self._graph(
            "ka treasury;\n"
            "vor withdrawal;\n"
            "fn main() { return }\n"
        )
        check_graph(graph)
        self.assertIsNotNone(graph.mir)
        self.assertTrue(graph.native_sigil_mir)

        graph.root_module.program = parse(
            "vor withdrawal;\n"
            "ka treasury;\n"
            "fn main() { return }\n"
        )
        with self.assertRaisesRegex(NativeSigilSemanticError, "ka is the genesis boundary"):
            check_graph(graph)

        self.assertIsNone(graph.mir)
        self.assertEqual(graph.native_sigil_mir, {})


if __name__ == "__main__":
    unittest.main()
