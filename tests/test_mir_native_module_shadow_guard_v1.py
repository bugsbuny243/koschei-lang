from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_native_runtime import inspect_native_mir_support
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError


class MirNativeModuleShadowGuardTests(unittest.TestCase):
    def checked_mir(self, files: dict[str, str]):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, source in files.items():
            (root / name).write_text(source, encoding="utf-8")
        graph = load_graph(root / "main.ks")
        check_graph(graph)
        return require_mir(graph)

    def test_local_binding_shadowing_import_is_not_admitted_as_module_member(self) -> None:
        mir = self.checked_mir(
            {
                "main.ks": (
                    "import lib\n"
                    "fn main() {\n"
                    "    let lib = [1, 2]\n"
                    "    println(lib.length())\n"
                    "}\n"
                ),
                "lib.ks": "fn value() -> Int { return 7 }\n",
            }
        )

        support = inspect_native_mir_support(mir)
        self.assertFalse(support.supported)
        self.assertTrue(
            any(
                "member access is not native-MIR yet" in reason
                for reason in support.reasons
            ),
            support.reasons,
        )

    def test_local_function_shadowing_import_fails_before_native_mir_admission(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "main.ks").write_text(
            "import lib\n"
            "fn lib() -> Int { return 9 }\n"
            "fn main() { println(lib.value()) }\n",
            encoding="utf-8",
        )
        (root / "lib.ks").write_text(
            "fn value() -> Int { return 7 }\n",
            encoding="utf-8",
        )
        graph = load_graph(root / "main.ks")

        # The typed-HIR boundary resolves the local function before module-member
        # admission and rejects `.value()` on Fn<Int>.  The unsafe shape therefore
        # never reaches direct MIR and must not be manufactured as a valid graph
        # merely to exercise the later support inspector.
        with self.assertRaises(SemanticError):
            check_graph(graph)


if __name__ == "__main__":
    unittest.main()
