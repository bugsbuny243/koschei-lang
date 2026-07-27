from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from koschei.mir import MIR_VERSION, MirIntegrityError, require_mir, to_dict
from koschei.modules import check_graph, load_graph


SOURCE = '''
fn countdown(value: Int) -> Int {
    if value == 0 {
        return 0
    }
    return countdown(value - 1)
}

fn main() {
    let mut value = 3
    while value > 0 {
        value = value - 1
    }
    println("resource contract ready")
}
'''


class ResourceContractsV5Tests(unittest.TestCase):
    def graph(self):
        directory = TemporaryDirectory()
        path = Path(directory.name) / "main.ks"
        path.write_text(SOURCE, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        self.addCleanup(directory.cleanup)
        return graph

    def test_mir_schema_is_v3(self):
        self.assertEqual(MIR_VERSION, 3)

    def test_resource_contract_is_visible(self):
        payload = to_dict(require_mir(self.graph()))
        functions = {
            item["name"]: item for item in payload["modules"][0]["functions"]
        }
        countdown = functions["countdown"]["resources"]
        main = functions["main"]["resources"]
        self.assertTrue(countdown["self_recursive"])
        self.assertGreater(main["backward_edges"], 0)
        self.assertGreater(main["instructions"], 0)
        self.assertEqual(main["basic_blocks"], functions["main"]["basic_blocks"])
        self.assertEqual(main["instructions"], functions["main"]["instructions"])
        self.assertEqual(main["ast_fallbacks"], functions["main"]["ast_fallbacks"])

    def test_forged_resource_contract_is_rejected(self):
        mir = require_mir(self.graph())
        module = mir.root_module
        function = module.functions[0]
        forged_resources = replace(function.resources, instructions=999999)
        forged_function = replace(function, resources=forged_resources)
        forged_module = replace(
            module,
            functions=(forged_function,) + module.functions[1:],
        )
        forged_modules = dict(mir.modules)
        forged_modules[mir.root] = forged_module
        forged = replace(mir, modules=forged_modules)
        with self.assertRaises(MirIntegrityError) as context:
            forged.assert_sealed()
        self.assertEqual(context.exception.code, "KS5002")

    def test_resource_contract_is_deterministic(self):
        first = to_dict(require_mir(self.graph()))
        second = to_dict(require_mir(self.graph()))
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(
            first["modules"][0]["functions"],
            second["modules"][0]["functions"],
        )

    def test_resource_contract_is_part_of_fingerprint(self):
        mir = require_mir(self.graph())
        module = mir.root_module
        function = module.functions[0]
        changed_resources = replace(function.resources, basic_blocks=999)
        changed_function = replace(function, resources=changed_resources)
        changed_module = replace(
            module,
            functions=(changed_function,) + module.functions[1:],
        )
        modules = dict(mir.modules)
        modules[mir.root] = changed_module
        changed = replace(mir, modules=modules)
        with self.assertRaises(MirIntegrityError):
            changed.assert_sealed()


if __name__ == "__main__":
    unittest.main()
