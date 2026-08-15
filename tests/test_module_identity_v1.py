from __future__ import annotations

import unittest
from pathlib import Path

from koschei.mir import require_mir
from koschei.modules import Module, ModuleGraph, check_graph
from koschei.parser import parse


ROOT_SOURCE = "import dep\nfn main() {}\n"
DEP_SOURCE = "fn helper() {}\n"


def _object_graph(root_path: str, dep_path: str) -> ModuleGraph:
    root_key = "koschei-object:11111111111111111111111111111111"
    dep_key = "koschei-object:22222222222222222222222222222222"
    dependency = Module(
        name="22222222222222222222222222222222",
        path=Path(dep_path),
        program=parse(DEP_SOURCE),
    )
    root = Module(
        name="11111111111111111111111111111111",
        path=Path(root_path),
        program=parse(ROOT_SOURCE),
        imports={"dep": dep_key},
    )
    return ModuleGraph(
        root=root_key,
        modules={root_key: root, dep_key: dependency},
    )


class ModuleIdentityTests(unittest.TestCase):
    def test_non_path_graph_keys_survive_full_check_and_mir_lowering(self) -> None:
        graph = _object_graph(
            "/diagnostic/epoch-1/root-a",
            "/diagnostic/epoch-1/dep-a",
        )
        report = check_graph(graph)
        self.assertEqual(report.functions, 1)

        mir = require_mir(graph)
        self.assertEqual(mir.root, graph.root)
        self.assertEqual(set(mir.modules), set(graph.modules))
        self.assertEqual(
            mir.root_module.imports["dep"],
            "koschei-object:22222222222222222222222222222222",
        )

    def test_physical_alias_rotation_does_not_change_mir_fingerprint(self) -> None:
        first = _object_graph(
            "/diagnostic/epoch-1/7a1b2c3d",
            "/diagnostic/epoch-1/0f9e8d7c",
        )
        second = _object_graph(
            "/diagnostic/epoch-2/91aa00ff",
            "/diagnostic/epoch-2/cceedd11",
        )

        check_graph(first)
        check_graph(second)

        self.assertEqual(
            require_mir(first).fingerprint,
            require_mir(second).fingerprint,
        )


if __name__ == "__main__":
    unittest.main()
