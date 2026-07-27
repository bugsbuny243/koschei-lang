from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from koschei.mir import MirIntegrityError, require_mir, to_dict
from koschei.modules import check_graph, load_graph


class MirEffectTests(unittest.TestCase):
    def mir_for(self, source: str):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / 'main.ks'
        path.write_text(source, encoding='utf-8')
        graph = load_graph(path)
        check_graph(graph)
        return directory, require_mir(graph)

    def test_direct_and_transitive_effects_are_inferred(self):
        source = '''
fn read_config(disk: DiskReadCaps, path: String) -> String or Error {
    return disk.read(path) or return Error("read")
}
fn load(disk: DiskReadCaps, path: String) -> String or Error {
    return read_config(disk, path) or return Error("load")
}
fn main() { println("ready") }
'''
        directory, mir = self.mir_for(source)
        try:
            functions = {item.name: item for item in mir.root_module.functions}
            self.assertEqual(functions['read_config'].effects, ('disk.read',))
            self.assertEqual(functions['load'].calls, ('read_config',))
            self.assertEqual(functions['load'].effects, ('disk.read',))
            self.assertEqual(functions['main'].effects, ())
        finally:
            directory.cleanup()

    def test_write_and_network_effects_are_distinct(self):
        source = '''
fn save(disk: DiskCaps, path: String, value: String) -> String or Error { disk.write(path, value) or return Error("write") return value }
fn fetch(net: NetCaps, url: String) -> String or Error { let r = net.get(url) or return Error("net") return r.text() }
fn main() { println("ok") }
'''
        directory, mir = self.mir_for(source)
        try:
            functions = {item.name: item for item in mir.root_module.functions}
            self.assertEqual(functions['save'].effects, ('disk.write',))
            self.assertEqual(functions['fetch'].effects, ('net',))
        finally:
            directory.cleanup()

    def test_effects_are_visible_in_json(self):
        source = '''
fn inspect(env: EnvCaps) -> String or Error { return env.get("TOKEN") or return Error("missing") }
fn main() { println("safe") }
'''
        directory, mir = self.mir_for(source)
        try:
            payload = to_dict(mir)
            inspect = next(item for item in payload['modules'][0]['functions'] if item['name'] == 'inspect')
            self.assertEqual(inspect['effects'], ['env.read'])
            self.assertEqual(payload['version'], 3)
        finally:
            directory.cleanup()

    def test_forged_effect_metadata_breaks_seal(self):
        directory, mir = self.mir_for('fn main() { println("safe") }\n')
        try:
            root = mir.root_module
            forged_function = replace(root.functions[0], effects=('net',))
            forged_root = replace(root, functions=(forged_function,))
            forged_modules = dict(mir.modules)
            forged_modules[mir.root] = forged_root
            forged = replace(mir, modules=forged_modules)
            with self.assertRaises(MirIntegrityError):
                forged.assert_sealed()
        finally:
            directory.cleanup()

    def test_recursive_call_graph_reaches_fixpoint(self):
        source = '''
fn a(disk: DiskReadCaps) -> String or Error { return b(disk) or return Error("a") }
fn b(disk: DiskReadCaps) -> String or Error { if true { return disk.read("x") or return Error("b") } return a(disk) }
fn main() { println("cycle") }
'''
        directory, mir = self.mir_for(source)
        try:
            functions = {item.name: item for item in mir.root_module.functions}
            self.assertEqual(functions['a'].effects, ('disk.read',))
            self.assertEqual(functions['b'].effects, ('disk.read',))
        finally:
            directory.cleanup()


if __name__ == '__main__':
    unittest.main()
