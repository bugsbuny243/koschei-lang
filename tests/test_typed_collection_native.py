from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from koschei.codegen_go import generate_go
from koschei.modules import check_graph, load_graph


@unittest.skipUnless(shutil.which("go"), "Go is not installed")
class TypedCollectionNativeTests(unittest.TestCase):
    def test_typed_collection_contracts_reach_native_backend(self) -> None:
        source = """
fn sum(values: List<Int>) -> Int {
    let mut total = 0
    for value in values {
        total = total + value
    }
    return total
}

fn read(values: Map<String, Int>) -> Int {
    return values.get("bonus") or 0
}

fn main() {
    println(sum([1, 2, 3]) + read({"bonus": 4}))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            check_graph(graph)
            (root / "main.go").write_text(
                generate_go(graph.root_module.program, graph), encoding="utf-8"
            )
            (root / "go.mod").write_text(
                "module typedcollections\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = root / "app"
            completed = subprocess.run(
                [shutil.which("go"), "build", "-o", str(binary), "."],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = subprocess.check_output([str(binary)], text=True)
            self.assertEqual(output.strip(), "10")


if __name__ == "__main__":
    unittest.main()
