from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from koschei import object_space_graph_v1 as graphmod
from koschei.object_space_graph_v1 import (
    ObjectSpaceGraphError,
    decode_object_space_graph,
    encode_object_space_graph_secret,
    load_object_space_module_graph,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceGraphAdversarialV1Tests(unittest.TestCase):
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
        self.secret = encode_object_space_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            target_by_import_slot={self.root_id: (self.lib_id,)},
        )

    def project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, _ = create_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                objects=self.objects,
                root_object_id=self.root_id,
                graph_secret=self.secret,
                temporal_policy=self.policy,
                now=self.now,
                project_id=self.project_id,
            )
            # The returned object is fully in-memory; keeping the temp directory is
            # unnecessary for graph parser attacks.
            return project

    def with_secret(self, project, secret: bytes):
        return replace(project, graph_secret=secret)

    def unpack_header(self, secret: bytes):
        return list(graphmod._HEADER.unpack_from(secret, 0))

    def replace_header(self, secret: bytes, fields) -> bytes:
        return graphmod._HEADER.pack(*fields) + secret[graphmod._HEADER.size:]

    def object_region_end(self, secret: bytes) -> int:
        fields = self.unpack_header(secret)
        count = fields[4]
        return graphmod._HEADER.size + count * graphmod._OBJECT.size

    def test_cross_project_graph_replay_is_rejected(self) -> None:
        project = self.project()
        replayed = replace(project, project_id=bytes.fromhex("bb" * 16))
        with self.assertRaisesRegex(ObjectSpaceGraphError, "another project"):
            decode_object_space_graph(replayed)

    def test_graph_magic_bitflip_is_rejected(self) -> None:
        project = self.project()
        secret = bytearray(project.graph_secret)
        secret[0] ^= 0x01
        with self.assertRaisesRegex(ObjectSpaceGraphError, "schema"):
            decode_object_space_graph(self.with_secret(project, bytes(secret)))

    def test_count_length_bomb_is_rejected_before_record_iteration(self) -> None:
        project = self.project()
        fields = self.unpack_header(project.graph_secret)
        fields[4] = graphmod.MAX_OBJECTS
        forged = self.replace_header(project.graph_secret, fields)
        with self.assertRaisesRegex(ObjectSpaceGraphError, "count/length"):
            decode_object_space_graph(self.with_secret(project, forged))

    def test_graph_object_digest_mismatch_against_k0_is_rejected(self) -> None:
        project = self.project()
        secret = bytearray(project.graph_secret)
        digest_offset = graphmod._HEADER.size + 16
        secret[digest_offset] ^= 0x01
        with self.assertRaisesRegex(ObjectSpaceGraphError, "differs from k0"):
            decode_object_space_graph(self.with_secret(project, bytes(secret)))

    def test_edge_target_digest_mismatch_is_rejected(self) -> None:
        project = self.project()
        secret = bytearray(project.graph_secret)
        edge_offset = self.object_region_end(project.graph_secret)
        digest_offset = edge_offset + 16 + 4 + 16
        secret[digest_offset] ^= 0x01
        with self.assertRaisesRegex(ObjectSpaceGraphError, "target digest mismatch"):
            decode_object_space_graph(self.with_secret(project, bytes(secret)))

    def test_unknown_edge_target_is_rejected(self) -> None:
        project = self.project()
        secret = bytearray(project.graph_secret)
        edge_offset = self.object_region_end(project.graph_secret)
        target_offset = edge_offset + 16 + 4
        secret[target_offset:target_offset + 16] = bytes.fromhex("ff" * 16)
        with self.assertRaisesRegex(ObjectSpaceGraphError, "unknown object"):
            decode_object_space_graph(self.with_secret(project, bytes(secret)))

    def test_duplicate_import_slot_is_rejected(self) -> None:
        project = self.project()
        fields = self.unpack_header(project.graph_secret)
        fields[5] = 2
        edge_offset = self.object_region_end(project.graph_secret)
        edge = project.graph_secret[edge_offset:edge_offset + graphmod._EDGE.size]
        forged = graphmod._HEADER.pack(*fields) + project.graph_secret[graphmod._HEADER.size:] + edge
        with self.assertRaisesRegex(ObjectSpaceGraphError, "duplicate import slot"):
            decode_object_space_graph(self.with_secret(project, forged))

    def test_hidden_extra_edge_not_backed_by_source_import_is_rejected(self) -> None:
        project = self.project()
        fields = self.unpack_header(project.graph_secret)
        fields[5] = 2
        edge_offset = self.object_region_end(project.graph_secret)
        source, _, target, target_digest = graphmod._EDGE.unpack_from(project.graph_secret, edge_offset)
        hidden = graphmod._EDGE.pack(source, 1, target, target_digest)
        forged = graphmod._HEADER.pack(*fields) + project.graph_secret[graphmod._HEADER.size:] + hidden
        poisoned = self.with_secret(project, forged)
        # Binary topology alone is valid/reachable. Admission to compiler semantics
        # must still reject the dormant edge because source has only one import.
        decode_object_space_graph(poisoned)
        with self.assertRaisesRegex(ObjectSpaceGraphError, "slots do not exactly match"):
            load_object_space_module_graph(poisoned)

    def test_missing_edge_makes_dependency_object_orphan_and_is_rejected(self) -> None:
        project = self.project()
        fields = self.unpack_header(project.graph_secret)
        fields[5] = 0
        edge_offset = self.object_region_end(project.graph_secret)
        forged = graphmod._HEADER.pack(*fields) + project.graph_secret[graphmod._HEADER.size:edge_offset]
        with self.assertRaisesRegex(ObjectSpaceGraphError, "unreachable/orphan"):
            decode_object_space_graph(self.with_secret(project, forged))

    def test_injected_cycle_is_rejected(self) -> None:
        project = self.project()
        fields = self.unpack_header(project.graph_secret)
        fields[5] = 2
        edge_offset = self.object_region_end(project.graph_secret)
        _, _, _, root_target_digest = graphmod._EDGE.unpack_from(project.graph_secret, edge_offset)
        del root_target_digest
        root_digest = next(
            record.artifact_digest for record in project.records if record.object_id == self.root_id
        )
        back_edge = graphmod._EDGE.pack(self.lib_id, 0, self.root_id, root_digest)
        forged = graphmod._HEADER.pack(*fields) + project.graph_secret[graphmod._HEADER.size:] + back_edge
        with self.assertRaisesRegex(ObjectSpaceGraphError, "dependency cycle"):
            decode_object_space_graph(self.with_secret(project, forged))

    def test_noncanonical_object_table_order_is_rejected(self) -> None:
        project = self.project()
        start = graphmod._HEADER.size
        first = project.graph_secret[start:start + graphmod._OBJECT.size]
        second = project.graph_secret[start + graphmod._OBJECT.size:start + 2 * graphmod._OBJECT.size]
        tail = project.graph_secret[start + 2 * graphmod._OBJECT.size:]
        forged = project.graph_secret[:start] + second + first + tail
        with self.assertRaisesRegex(ObjectSpaceGraphError, "object table is not canonical"):
            decode_object_space_graph(self.with_secret(project, forged))

    def test_filesystem_sibling_import_resolver_is_never_consulted(self) -> None:
        project = self.project()
        with patch(
            "koschei.modules._resolve_sibling_import",
            side_effect=AssertionError("Object Space attempted legacy sibling resolution"),
        ):
            graph = load_object_space_module_graph(project)
        self.assertEqual(graph.root, self.root_id.hex())
        self.assertEqual(graph.root_module.imports["lib"], self.lib_id.hex())


if __name__ == "__main__":
    unittest.main()
