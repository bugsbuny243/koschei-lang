from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
import tempfile
import unittest

from koschei.mir import MirGraph, MirIntegrityError, to_dict
from koschei.modules import check_graph, load_graph


class NativeSigilCanonicalMirSealTests(unittest.TestCase):
    def _checked_mir(self, path: Path, source: str) -> MirGraph:
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        self.assertIsInstance(graph.mir, MirGraph)
        return graph.mir

    def test_checked_native_roots_are_embedded_in_canonical_mir_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "root.ks"
            mir = self._checked_mir(path, "ka treasury;\nvor treasury;\n")

            native = mir.root_module.native_sigils
            self.assertIsNotNone(native)
            assert native is not None
            self.assertEqual(
                tuple((item.sigil, item.subject) for item in native.bindings),
                (("ka", "treasury"), ("vor", "treasury")),
            )
            self.assertTrue(native.universe_plan_digest)
            self.assertTrue(native.fingerprint)

            output = to_dict(mir)
            emitted = output["modules"][0]["native_sigils"]
            self.assertIsNotNone(emitted)
            self.assertEqual(emitted["fingerprint"], native.fingerprint)

    def test_native_source_cannot_remain_sealed_if_canonical_mir_loses_sigil_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "root.ks"
            mir = self._checked_mir(path, "ka treasury;\nvor treasury;\n")

            stripped_module = replace(mir.root_module, native_sigils=None)
            modules = dict(mir.modules)
            modules[mir.root] = stripped_module
            stripped = replace(mir, modules=MappingProxyType(modules))

            with self.assertRaisesRegex(
                MirIntegrityError,
                "native sigil semantics missing from canonical MIR module",
            ):
                stripped.assert_sealed()

    def test_native_sigil_semantic_change_changes_canonical_mir_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "root.ks"
            treasury = self._checked_mir(path, "ka treasury;\nvor treasury;\n")
            vault = self._checked_mir(path, "ka vault;\nvor vault;\n")
            self.assertNotEqual(treasury.fingerprint, vault.fingerprint)

    def test_native_sigil_line_shift_does_not_change_canonical_mir_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "root.ks"
            first = self._checked_mir(path, "ka treasury;\nvor treasury;\n")
            shifted = self._checked_mir(path, "\n\nka treasury;\nvor treasury;\n")
            self.assertEqual(first.fingerprint, shifted.fingerprint)


if __name__ == "__main__":
    unittest.main()
