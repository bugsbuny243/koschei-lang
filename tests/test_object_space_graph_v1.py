from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.object_space_graph_v1 import (
    check_object_space_graph,
    decode_object_space_graph,
    encode_object_space_graph_secret,
    load_object_space_module_graph,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceGraphV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("aa" * 16)
        self.root_id = bytes.fromhex("11" * 16)
        self.lib_id = bytes.fromhex("22" * 16)
        self.objects = {
            self.root_id: b"import lib\nfn main() { let x = lib.f() }\n",
            self.lib_id: b"fn f() -> Int { return 7 }\n",
        }
        self.graph_secret = encode_object_space_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            target_by_import_slot={self.root_id: (self.lib_id,)},
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.graph_secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def test_persistent_graph_secret_contains_no_logical_import_or_source_text(self) -> None:
        self.assertNotIn(b"lib", self.graph_secret)
        self.assertNotIn(b"fn main", self.graph_secret)
        self.assertNotIn(b"fn f", self.graph_secret)
        self.assertIn(self.root_id, self.graph_secret)
        self.assertIn(self.lib_id, self.graph_secret)

    def test_graph_round_trip_matches_k0_object_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            objects, edges = decode_object_space_graph(loaded)
            self.assertEqual({object_id for object_id, _ in objects}, set(self.objects))
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].source_object_id, self.root_id)
            self.assertEqual(edges[0].import_ordinal, 0)
            self.assertEqual(edges[0].target_object_id, self.lib_id)

    def test_module_graph_identity_is_object_id_not_path_or_logical_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, _ = self.create(root)
            graph = load_object_space_module_graph(project)
            self.assertEqual(graph.root, self.root_id.hex())
            self.assertEqual(set(graph.modules), {self.root_id.hex(), self.lib_id.hex()})
            self.assertEqual(
                graph.modules[self.root_id.hex()].imports,
                {"lib": self.lib_id.hex()},
            )
            for module in graph.modules.values():
                self.assertFalse(module.path.exists())
                self.assertNotIn("k1", str(module.path))
                self.assertNotIn(".ks", str(module.path))

    def test_existing_check_pipeline_accepts_object_identity_graph_and_seals_mir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, _ = self.create(root)
            graph, report = check_object_space_graph(project)
            self.assertIsNotNone(report)
            self.assertIsNotNone(graph.mir)
            self.assertEqual(graph.root, self.root_id.hex())
            mir_keys = set(graph.mir.modules)
            self.assertEqual(mir_keys, {self.root_id.hex(), self.lib_id.hex()})

    def test_epoch_rotation_preserves_graph_semantics_while_locators_rotate(self) -> None:
        from koschei.object_space_v1 import rotate_object_space_epoch

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            old_locators = {record.object_id: record.locator for record in project.records}
            rotated, _ = rotate_object_space_epoch(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            new_locators = {record.object_id: record.locator for record in rotated.records}
            self.assertEqual(rotated.graph_secret, project.graph_secret)
            self.assertEqual(set(old_locators), set(new_locators))
            self.assertTrue(all(old_locators[key] != new_locators[key] for key in old_locators))
            graph, _ = check_object_space_graph(rotated)
            self.assertEqual(graph.root, self.root_id.hex())


if __name__ == "__main__":
    unittest.main()
