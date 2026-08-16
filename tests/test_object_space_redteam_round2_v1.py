from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from koschei import object_space_v1 as space
from koschei.object_space_redteam_round2_v1 import MAX_PHYSICAL_CELLS_V1
from koschei.object_space_v1 import (
    ObjectSpaceError,
    create_object_space_project,
    load_object_space_project,
    rotate_object_space_epoch,
)
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceRedTeamRound2V1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.root_id = bytes.fromhex("11" * 16)
        self.worker_id = bytes.fromhex("22" * 16)
        self.objects = {
            self.root_id: b"ROOT-ROUND2",
            self.worker_id: b"WORKER-ROUND2",
        }

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=b"round2-secret-graph",
            temporal_policy=self.policy,
            now=self.now,
        )

    def load(self, root: Path, project, handle):
        return load_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=project.project_id,
            expected_epoch=project.epoch,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_k1_path_swap_before_commit_is_rejected_without_authority_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            original_k0 = (root / "k0").read_bytes()
            admitted_store = root / "k1"
            moved_store = root / "k1-admitted"
            fired = False

            def swap_store(purpose, _aad, _plaintext) -> None:
                nonlocal fired
                if fired or purpose != space._OBJECT_PURPOSE:
                    return
                fired = True
                os.rename(admitted_store, moved_store)
                admitted_store.mkdir(mode=0o700)

            self.provider.before_seal = swap_store
            with self.assertRaisesRegex(ObjectSpaceError, "k1 path identity changed"):
                rotate_object_space_epoch(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )
            self.provider.before_seal = None

            self.assertEqual((root / "k0").read_bytes(), original_k0)
            # Restore the public locator and prove epoch 1 remained authoritative.
            admitted_store.rmdir()
            os.rename(moved_store, admitted_store)
            loaded = self.load(root, project, handle)
            self.assertEqual(loaded.epoch, 1)
            self.assertEqual(loaded.object_payloads, project.object_payloads)

    def test_truncated_k0_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            payload = (root / "k0").read_bytes()
            (root / "k0").write_bytes(payload[: max(1, len(payload) // 3)])
            with self.assertRaises(ObjectSpaceError):
                self.load(root, project, handle)

    def test_oversized_k0_is_rejected_before_provider_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            calls = 0
            original_open = self.provider.open

            def counted_open(**kwargs):
                nonlocal calls
                calls += 1
                return original_open(**kwargs)

            self.provider.open = counted_open
            (root / "k0").write_bytes(b"X" * (space.MAX_SEALED_ROOT_BYTES + 1))
            with self.assertRaises(ObjectSpaceError):
                self.load(root, project, handle)
            self.assertEqual(calls, 0)

    def test_truncated_authoritative_cell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            record = project.records[0]
            cell = root / "k1" / record.locator_text
            payload = cell.read_bytes()
            cell.write_bytes(payload[: max(1, len(payload) // 2)])
            with self.assertRaises(ObjectSpaceError):
                self.load(root, project, handle)

    def test_opaque_decoy_flood_hits_hard_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            store = root / "k1"
            existing = set(os.listdir(store))
            needed = (MAX_PHYSICAL_CELLS_V1 + 1) - len(existing)
            for index in range(needed):
                name = f"{index:064x}"
                if name in existing:
                    continue
                (store / name).write_bytes(b"")
            with self.assertRaisesRegex(ObjectSpaceError, "physical cell budget"):
                self.load(root, project, handle)


if __name__ == "__main__":
    unittest.main()
