from __future__ import annotations

import copy
import unittest

from koschei.epoch_alias_rotation_v1 import (
    AliasRotationError,
    derive_epoch_alias,
    rotate_graph_payload,
)


class EpochAliasRotationV1Tests(unittest.TestCase):
    def payload(self):
        return {
            "schema": "koschei.opaque-source-graph/v1",
            "project_id": "p-01",
            "objects": [
                {
                    "object_id": "0123456789abcdef0123456789abcdef",
                    "artifact_hash": "sha256:" + "a" * 64,
                    "policy_hash": "sha256:" + "b" * 64,
                    "epoch_alias": "OLDALIAS1",
                    "provenance": "canonical",
                    "requested_capabilities": ["net.read"],
                },
                {
                    "object_id": "fedcba9876543210fedcba9876543210",
                    "artifact_hash": "sha256:" + "c" * 64,
                    "policy_hash": "sha256:" + "b" * 64,
                    "epoch_alias": "OLDALIAS2",
                    "provenance": "canonical",
                    "requested_capabilities": [],
                },
            ],
            "edges": [
                {
                    "from_object_id": "0123456789abcdef0123456789abcdef",
                    "import_name": "dep",
                    "to_object_id": "fedcba9876543210fedcba9876543210",
                    "expected_artifact_hash": "sha256:" + "c" * 64,
                    "requested_capabilities": [],
                }
            ],
            "constraints": {
                "physical_path_is_authority": False,
                "semantic_filename_required": False,
                "plaintext_fallback_allowed": False,
                "decoy_is_deployable": False,
            },
        }

    def test_same_epoch_and_key_is_deterministic(self):
        key = b"r" * 32
        one = derive_epoch_alias(
            project_id="p-01",
            object_id="0123456789abcdef0123456789abcdef",
            epoch=41,
            rotation_key=key,
        )
        two = derive_epoch_alias(
            project_id="p-01",
            object_id="0123456789abcdef0123456789abcdef",
            epoch=41,
            rotation_key=key,
        )
        self.assertEqual(one, two)
        self.assertGreaterEqual(len(one), 9)
        self.assertNotIn("auth", one.lower())

    def test_new_epoch_changes_only_physical_alias_identity(self):
        original = self.payload()
        before = copy.deepcopy(original)
        rotated, moves = rotate_graph_payload(original, epoch=42, rotation_key=b"r" * 32)

        self.assertEqual(original, before, "rotation must not mutate admitted graph input")
        self.assertEqual(rotated["storage_epoch"], 42)
        self.assertEqual(len({item["epoch_alias"] for item in rotated["objects"]}), 2)
        self.assertTrue(all(move.old_alias != move.new_alias for move in moves))

        for old, new in zip(before["objects"], rotated["objects"]):
            for field in (
                "object_id",
                "artifact_hash",
                "policy_hash",
                "provenance",
                "requested_capabilities",
            ):
                self.assertEqual(old[field], new[field])
        self.assertEqual(before["edges"], rotated["edges"])
        self.assertEqual(before["constraints"], rotated["constraints"])

    def test_different_epochs_produce_different_alias_sets(self):
        graph = self.payload()
        first, _ = rotate_graph_payload(graph, epoch=100, rotation_key=b"k" * 32)
        second, _ = rotate_graph_payload(graph, epoch=101, rotation_key=b"k" * 32)
        self.assertNotEqual(
            [item["epoch_alias"] for item in first["objects"]],
            [item["epoch_alias"] for item in second["objects"]],
        )

    def test_rotation_key_is_independent_and_strong(self):
        with self.assertRaises(AliasRotationError):
            rotate_graph_payload(self.payload(), epoch=1, rotation_key=b"short")

    def test_invalid_epoch_fails_closed(self):
        with self.assertRaises(AliasRotationError):
            rotate_graph_payload(self.payload(), epoch=-1, rotation_key=b"r" * 32)


if __name__ == "__main__":
    unittest.main()
