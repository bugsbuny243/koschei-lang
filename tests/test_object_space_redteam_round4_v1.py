from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei import object_space_v1 as space
from koschei.object_space_v1 import create_object_space_project, load_object_space_project, rotate_object_space_epoch
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceRedTeamRound4V1Tests(unittest.TestCase):
    """Scale attacks that small object graphs cannot expose."""

    def test_full_cleanup_failure_does_not_brick_large_rotated_reality(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000

        # 3000 objects deliberately exceed the v2 inert allowance after one full
        # stale generation is left behind (3000 new + 3000 old > 5120).
        objects: dict[bytes, bytes] = {}
        for index in range(1, 3001):
            object_id = index.to_bytes(16, "big")
            objects[object_id] = b"x" + index.to_bytes(4, "big")
        root_id = (1).to_bytes(16, "big")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = create_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=b"round4-large-graph",
                temporal_policy=policy,
                now=now,
            )
            self.assertEqual(len(project.records), 3000)

            # Simulate total best-effort stale-cell cleanup failure after k0 has
            # already switched to epoch 2.
            with patch(
                "koschei.object_space_adversarial_guard_v1._space._unlink_at",
                side_effect=OSError("injected full stale-generation cleanup failure"),
            ):
                rotated, new_handle = rotate_object_space_epoch(
                    root,
                    provider=provider,
                    temporal_key=temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=1,
                    temporal_policy=policy,
                    now=now,
                )

            self.assertEqual(rotated.epoch, 2)
            self.assertEqual(len(rotated.records), 3000)
            self.assertGreaterEqual(len(rotated.unreferenced_locators), 3000)

            # The new authoritative reality must remain loadable even though the
            # entire previous physical generation survived cleanup.
            reloaded = load_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                temporal_handle=new_handle,
                expected_project_id=project.project_id,
                expected_epoch=2,
                temporal_policy=policy,
                now=now,
            )
            self.assertEqual(reloaded.object_payloads, project.object_payloads)


if __name__ == "__main__":
    unittest.main()
