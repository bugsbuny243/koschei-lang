from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.native_relationship_v1 import (
    NativeRelationshipError,
    NativeRelationshipSpecV1,
    _HEADER,
    _OBJECT,
    _RELATION,
    decode_native_relationship_graph,
    encode_native_relationship_graph_secret,
)
from koschei.object_space_frontend_identity_v1 import FRONTEND_GRAPH_MAGIC_V1
from koschei.object_space_v1 import create_object_space_project, rotate_object_space_epoch
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeRelationshipAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("b1" * 16)
        self.root_id = bytes.fromhex("b2" * 16)
        self.target_id = bytes.fromhex("b3" * 16)
        self.relation_id = bytes.fromhex("b4" * 16)
        self.root_source = b"witness remote conduit 0\nwitness fee 2\nwitness total sum remote fee\nresolve total\n"
        self.target_source = b"witness base 20\nwitness doubled product base 2\nresolve doubled\n"
        self.objects = {self.root_id: self.root_source, self.target_id: self.target_source}

    def spec(self, **changes):
        values = dict(
            relation_id=self.relation_id,
            slot=0,
            target_object_id=self.target_id,
            issued_epoch=1,
            expires_epoch=4,
            authority_ceiling=0,
            effect_ceiling=0,
            max_target_witnesses=2,
            max_abs_value=40,
        )
        values.update(changes)
        return NativeRelationshipSpecV1(**values)

    def secret(self, *, objects=None, relationships=None):
        return encode_native_relationship_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects if objects is None else objects,
            current_epoch=1,
            relationships=(self.spec(),) if relationships is None else relationships,
        )

    def create(self, root: Path, *, secret=None, objects=None, project_id=None):
        actual_objects = self.objects if objects is None else objects
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=actual_objects,
            root_object_id=self.root_id,
            graph_secret=self.secret(objects=actual_objects) if secret is None else secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id if project_id is None else project_id,
        )

    def test_target_payload_substitution_is_rejected_against_k0_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space")
            forged_payloads = dict(project.object_payloads)
            forged_payloads[self.target_id] = b"witness v 99\nresolve v\n"
            forged = replace(project, object_payloads=forged_payloads)
            with self.assertRaisesRegex(NativeRelationshipError, "digest"):
                decode_native_relationship_graph(forged)

    def test_cross_project_relationship_secret_replay_is_rejected(self) -> None:
        other_project = bytes.fromhex("b5" * 16)
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(
                Path(temporary) / "other",
                secret=self.secret(),
                project_id=other_project,
            )
            with self.assertRaisesRegex(NativeRelationshipError, "another project"):
                decode_native_relationship_graph(project)

    def test_relation_expires_after_storage_epoch_rotation(self) -> None:
        expiring = self.secret(relationships=(self.spec(expires_epoch=1),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root, secret=expiring)
            rotated, _ = rotate_object_space_epoch(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=project.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            self.assertEqual(rotated.epoch, 2)
            with self.assertRaisesRegex(NativeRelationshipError, "stale"):
                decode_native_relationship_graph(rotated)

    def test_authority_and_effect_inflation_fail_before_graph_creation(self) -> None:
        for changes in ({"authority_ceiling": 1}, {"effect_ceiling": 1}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(NativeRelationshipError, "zero authority"):
                    self.secret(relationships=(self.spec(**changes),))

    def test_resource_ceiling_blocks_witness_and_value_inflation(self) -> None:
        with self.assertRaisesRegex(NativeRelationshipError, "witness resource ceiling"):
            self.secret(relationships=(self.spec(max_target_witnesses=1),))
        with self.assertRaisesRegex(NativeRelationshipError, "value exceeds"):
            self.secret(relationships=(self.spec(max_abs_value=39),))

    def test_root_as_target_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(NativeRelationshipError, "non-root"):
            self.secret(relationships=(self.spec(target_object_id=self.root_id),))

    def test_orphan_leaf_and_hidden_relation_slot_fail_closed(self) -> None:
        extra_id = bytes.fromhex("b6" * 16)
        objects = dict(self.objects)
        objects[extra_id] = b"witness v 1\nresolve v\n"
        with self.assertRaisesRegex(NativeRelationshipError, "orphan"):
            self.secret(objects=objects, relationships=(self.spec(),))

        extra_relation = NativeRelationshipSpecV1(
            relation_id=bytes.fromhex("b7" * 16),
            slot=1,
            target_object_id=extra_id,
            issued_epoch=1,
            expires_epoch=4,
            max_target_witnesses=1,
            max_abs_value=1,
        )
        with self.assertRaisesRegex(NativeRelationshipError, "conduit set"):
            self.secret(objects=objects, relationships=(self.spec(), extra_relation))

    def test_legacy_import_and_legacy_target_cannot_smuggle_through_relationship(self) -> None:
        bad_root = dict(self.objects)
        bad_root[self.root_id] = self.root_source + b"import worker\n"
        with self.assertRaises(Exception):
            self.secret(objects=bad_root)

        bad_target = dict(self.objects)
        bad_target[self.target_id] = b"fn main() { return 40 }\n"
        with self.assertRaises(Exception):
            self.secret(objects=bad_target)

    def test_exact_relationship_magic_downgrade_does_not_source_sniff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space")
            payload = bytearray(project.graph_secret)
            self.assertEqual(len(FRONTEND_GRAPH_MAGIC_V1), 16)
            payload[:16] = FRONTEND_GRAPH_MAGIC_V1
            downgraded = replace(project, graph_secret=bytes(payload))
            with patch(
                "koschei.object_space_frontend_identity_v1.check_native_kernel",
                side_effect=AssertionError("native source sniff reached after relationship downgrade"),
            ):
                with self.assertRaises(Exception) as caught:
                    from koschei.native_relationship_alignment_v1 import check_object_space_graph_with_native_relationships
                    check_object_space_graph_with_native_relationships(downgraded)
            self.assertNotIsInstance(caught.exception, AssertionError)

    def test_noncanonical_relationship_table_reordering_is_rejected(self) -> None:
        second_id = bytes.fromhex("b8" * 16)
        second_relation_id = bytes.fromhex("b9" * 16)
        objects = dict(self.objects)
        objects[second_id] = b"witness v 1\nresolve v\n"
        objects[self.root_id] = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        specs = (
            self.spec(),
            NativeRelationshipSpecV1(
                relation_id=second_relation_id,
                slot=1,
                target_object_id=second_id,
                issued_epoch=1,
                expires_epoch=4,
                max_target_witnesses=1,
                max_abs_value=1,
            ),
        )
        secret = self.secret(objects=objects, relationships=specs)
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space", secret=secret, objects=objects)
            start = _HEADER.size + len(objects) * _OBJECT.size
            first = project.graph_secret[start : start + _RELATION.size]
            second = project.graph_secret[start + _RELATION.size : start + 2 * _RELATION.size]
            tampered = (
                project.graph_secret[:start]
                + second
                + first
                + project.graph_secret[start + 2 * _RELATION.size :]
            )
            forged = replace(project, graph_secret=tampered)
            with self.assertRaisesRegex(NativeRelationshipError, "not canonical"):
                decode_native_relationship_graph(forged)


if __name__ == "__main__":
    unittest.main()
