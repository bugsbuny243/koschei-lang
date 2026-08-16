from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from koschei.modules import check_graph
from koschei.native_reality_graph_epoch_v1 import (
    rotate_native_reality_graph_epoch,
)
from koschei.native_reality_graph_v1 import (
    create_native_reality_graph_project,
    load_native_reality_graph_project,
)
from koschei.native_reality_v1 import NativeRealityError


SEAL_KEY = bytes.fromhex(
    "f38f6ac88bb9ccf847f5ef5fd27d8f20"
    "824c76532f9a145baad4619e813e73c1"
)

SOURCES = {
    "app": "import util\nfn main() {}\n",
    "util": "fn helper() {}\n",
}


class NativeRealityGraphEpochTests(unittest.TestCase):
    def create(self, root: Path):
        return create_native_reality_graph_project(
            root,
            seal_key=SEAL_KEY,
            sources=SOURCES,
            root_label="app",
        )

    def test_rotation_changes_all_physical_aliases_not_canonical_objects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            before = project.reality_project.reality
            old_object_aliases = {
                item.object_id: item.alias_text for item in project.objects
            }
            old_object_digests = {
                item.object_id: item.artifact_digest for item in project.objects
            }
            old_graph_alias = project.graph_alias
            old_paths = {
                project.reality_project.matter_root / alias
                for alias in old_object_aliases.values()
            }
            old_paths.add(project.reality_project.matter_root / old_graph_alias)

            rotated = rotate_native_reality_graph_epoch(
                project.reality_project.root,
                seal_key=SEAL_KEY,
                expected_project_id=before.project_id,
                expected_epoch=1,
            )
            after = rotated.reality_project.reality

            self.assertEqual(after.epoch, 2)
            self.assertEqual(after.project_id, before.project_id)
            self.assertEqual(after.root_object_id, before.root_object_id)
            self.assertEqual(after.artifact_digest, before.artifact_digest)
            self.assertNotEqual(rotated.graph_alias, old_graph_alias)
            self.assertEqual(
                {item.object_id for item in rotated.objects},
                set(old_object_aliases),
            )
            for item in rotated.objects:
                self.assertEqual(
                    item.artifact_digest,
                    old_object_digests[item.object_id],
                )
                self.assertNotEqual(
                    item.alias_text,
                    old_object_aliases[item.object_id],
                )

            self.assertTrue(all(not path.exists() for path in old_paths))
            check_graph(rotated.module_graph)

            with self.assertRaisesRegex(NativeRealityError, "temporal context"):
                load_native_reality_graph_project(
                    rotated.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=after.project_id,
                    expected_epoch=1,
                )

    def test_rotated_capsule_still_does_not_persist_logical_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            rotated = rotate_native_reality_graph_epoch(
                project.reality_project.root,
                seal_key=SEAL_KEY,
                expected_project_id=project.reality_project.reality.project_id,
                expected_epoch=1,
            )
            capsule = (
                rotated.reality_project.matter_root / rotated.graph_alias
            ).read_bytes()
            self.assertNotIn(b"app", capsule)
            self.assertNotIn(b"util", capsule)

    def test_stale_second_rotation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            rotate_native_reality_graph_epoch(
                project.reality_project.root,
                seal_key=SEAL_KEY,
                expected_project_id=project.reality_project.reality.project_id,
                expected_epoch=1,
            )
            with self.assertRaisesRegex(NativeRealityError, "temporal context"):
                rotate_native_reality_graph_epoch(
                    project.reality_project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality_project.reality.project_id,
                    expected_epoch=1,
                )

    def test_failed_commit_cleans_new_aliases_and_keeps_old_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "demo")
            matter = project.reality_project.matter_root
            before_names = {path.name for path in matter.iterdir()}
            before_reality = project.reality_project.reality_path.read_bytes()

            with patch(
                "koschei.native_reality_graph_epoch_v1._replace_sealed_at",
                side_effect=OSError("injected switch failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected switch failure"):
                    rotate_native_reality_graph_epoch(
                        project.reality_project.root,
                        seal_key=SEAL_KEY,
                        expected_project_id=project.reality_project.reality.project_id,
                        expected_epoch=1,
                    )

            self.assertEqual(
                {path.name for path in matter.iterdir()},
                before_names,
            )
            self.assertEqual(
                project.reality_project.reality_path.read_bytes(),
                before_reality,
            )
            restored = load_native_reality_graph_project(
                project.reality_project.root,
                seal_key=SEAL_KEY,
                expected_project_id=project.reality_project.reality.project_id,
                expected_epoch=1,
            )
            check_graph(restored.module_graph)


if __name__ == "__main__":
    unittest.main()
