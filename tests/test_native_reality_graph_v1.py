from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from koschei.mir import require_mir
from koschei.modules import ModuleError, check_graph
from koschei.native_reality_graph_v1 import (
    GraphEdge,
    NativeRealityGraphError,
    _decode_capsule,
    _encode_capsule,
    _slot_tag,
    create_native_reality_graph_project,
    load_native_reality_graph_project,
)


SEAL_KEY = bytes.fromhex(
    "f38f6ac88bb9ccf847f5ef5fd27d8f20"
    "824c76532f9a145baad4619e813e73c1"
)

SOURCES = {
    "app": "import util\nfn main() {}\n",
    "util": "fn helper() {}\n",
}


class NativeRealityGraphTests(unittest.TestCase):
    def create(self, root: Path):
        return create_native_reality_graph_project(
            root,
            seal_key=SEAL_KEY,
            sources=SOURCES,
            root_label="app",
        )

    def test_create_load_and_full_compiler_check_use_object_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            graph = project.module_graph

            self.assertEqual(len(project.objects), 2)
            self.assertEqual(len(project.edges), 1)
            self.assertEqual(len(graph.modules), 2)
            self.assertTrue(graph.root.startswith("koschei-object:"))
            self.assertTrue(all(key.startswith("koschei-object:") for key in graph.modules))

            report = check_graph(graph)
            self.assertEqual(report.functions, 1)
            mir = require_mir(graph)
            self.assertEqual(mir.root, graph.root)
            self.assertEqual(set(mir.modules), set(graph.modules))

            reloaded = load_native_reality_graph_project(
                project.reality_project.root,
                seal_key=SEAL_KEY,
                expected_project_id=project.reality_project.reality.project_id,
                expected_epoch=1,
            )
            check_graph(reloaded.module_graph)
            self.assertEqual(
                set(reloaded.module_graph.modules),
                set(project.module_graph.modules),
            )

    def test_persistent_graph_does_not_store_logical_labels_as_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            matter = project.reality_project.matter_root
            names = sorted(path.name for path in matter.iterdir())

            self.assertEqual(len(names), 3)
            for name in names:
                self.assertRegex(name, r"^[0-9a-f]{32}$")
                self.assertNotIn("app", name)
                self.assertNotIn("util", name)

            capsule = (matter / project.graph_alias).read_bytes()
            self.assertNotIn(b"app", capsule)
            self.assertNotIn(b"util", capsule)

    def test_wrong_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            with self.assertRaises(Exception):
                load_native_reality_graph_project(
                    project.reality_project.root,
                    seal_key=b"x" * 32,
                    expected_project_id=project.reality_project.reality.project_id,
                    expected_epoch=1,
                )

    def test_graph_capsule_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            capsule_path = project.reality_project.matter_root / project.graph_alias
            payload = bytearray(capsule_path.read_bytes())
            payload[-1] ^= 1
            capsule_path.write_bytes(payload)

            with self.assertRaisesRegex(
                NativeRealityGraphError,
                "authentication failed",
            ):
                load_native_reality_graph_project(
                    project.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality_project.reality.project_id,
                    expected_epoch=1,
                )

    def test_non_root_source_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            root_id = project.reality_project.reality.root_object_id
            target = next(item for item in project.objects if item.object_id != root_id)
            path = project.reality_project.matter_root / target.alias_text
            path.write_bytes(path.read_bytes() + b"\n// tamper")

            with self.assertRaisesRegex(
                NativeRealityGraphError,
                "source object hash mismatch",
            ):
                load_native_reality_graph_project(
                    project.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality_project.reality.project_id,
                    expected_epoch=1,
                )

    def test_cross_project_capsule_substitution_fails_even_with_same_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.create(root / "first")
            second = self.create(root / "second")

            first_capsule = (
                first.reality_project.matter_root / first.graph_alias
            ).read_bytes()
            second_capsule = second.reality_project.matter_root / second.graph_alias
            second_capsule.write_bytes(first_capsule)

            with self.assertRaisesRegex(
                NativeRealityGraphError,
                "authentication failed",
            ):
                load_native_reality_graph_project(
                    second.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=second.reality_project.reality.project_id,
                    expected_epoch=1,
                )

    def test_validly_sealed_hidden_edge_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            reality = project.reality_project.reality
            capsule_path = project.reality_project.matter_root / project.graph_alias
            objects, edges = _decode_capsule(
                capsule_path.read_bytes(),
                seal_key=SEAL_KEY,
                expected_project_id=reality.project_id,
                expected_epoch=1,
                expected_root_object_id=reality.root_object_id,
                expected_root_artifact_digest=reality.artifact_digest,
            )
            root_object = next(
                item for item in objects if item.object_id == reality.root_object_id
            )
            target = next(item for item in objects if item.object_id != reality.root_object_id)
            hidden = GraphEdge(
                from_object_id=root_object.object_id,
                slot_tag=_slot_tag(
                    SEAL_KEY,
                    reality.project_id,
                    root_object.object_id,
                    "hidden",
                ),
                to_object_id=target.object_id,
                expected_artifact_digest=target.artifact_digest,
            )
            capsule_path.write_bytes(
                _encode_capsule(
                    seal_key=SEAL_KEY,
                    project_id=reality.project_id,
                    epoch=1,
                    root_object_id=reality.root_object_id,
                    root_artifact_digest=reality.artifact_digest,
                    objects=objects,
                    edges=edges + (hidden,),
                )
            )

            with self.assertRaisesRegex(
                NativeRealityGraphError,
                "edge slots not present",
            ):
                load_native_reality_graph_project(
                    project.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=reality.project_id,
                    expected_epoch=1,
                )

    def test_missing_import_target_fails_before_project_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            with self.assertRaises(ModuleError) as raised:
                create_native_reality_graph_project(
                    root,
                    seal_key=SEAL_KEY,
                    sources={"app": "import missing\nfn main() {}\n"},
                    root_label="app",
                )
            self.assertEqual(raised.exception.code, "KS1601")
            self.assertFalse(root.exists())

    def test_cycle_fails_before_project_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            with self.assertRaisesRegex(NativeRealityGraphError, "cycle"):
                create_native_reality_graph_project(
                    root,
                    seal_key=SEAL_KEY,
                    sources={
                        "a": "import b\nfn main() {}\n",
                        "b": "import a\nfn helper() {}\n",
                    },
                    root_label="a",
                )
            self.assertFalse(root.exists())

    def test_orphan_source_fails_before_project_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            with self.assertRaisesRegex(
                NativeRealityGraphError,
                "unreachable",
            ):
                create_native_reality_graph_project(
                    root,
                    seal_key=SEAL_KEY,
                    sources={
                        "app": "fn main() {}\n",
                        "orphan": "fn helper() {}\n",
                    },
                    root_label="app",
                )
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
