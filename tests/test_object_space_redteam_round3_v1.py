from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from koschei import object_space_v1 as space
from koschei.object_space_redteam_round3_v1 import _MAX_ROOT_PLAINTEXT_V1
from koschei.object_space_v1 import (
    ObjectSpaceError,
    create_object_space_project,
    load_object_space_project,
)
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceRedTeamRound3V1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.root_id = bytes.fromhex("11" * 16)
        self.worker_id = bytes.fromhex("22" * 16)
        self.audit_id = bytes.fromhex("33" * 16)
        self.objects = {
            self.root_id: b"ROOT-ROUND3",
            self.worker_id: b"WORKER-ROUND3",
            self.audit_id: b"AUDIT-ROUND3",
        }

    def create(self, root: Path, *, provider=None):
        return create_object_space_project(
            root,
            provider=self.provider if provider is None else provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=b"round3-secret-graph",
            temporal_policy=self.policy,
            now=self.now,
        )

    def load(self, root: Path, project, handle, *, provider=None):
        return load_object_space_project(
            root,
            provider=self.provider if provider is None else provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=project.project_id,
            expected_epoch=project.epoch,
            temporal_policy=self.policy,
            now=self.now,
        )

    def _provider_open_counter(self):
        calls = {"count": 0}
        original = self.provider.open

        def counted_open(**kwargs):
            calls["count"] += 1
            return original(**kwargs)

        self.provider.open = counted_open
        return calls

    def _forge_root_plaintext(self, root: Path, project, transform) -> None:
        aad = space._root_aad(project.project_id, project.epoch)
        sealed = (root / "k0").read_bytes()
        plaintext = self.provider.open(
            purpose=space._ROOT_PURPOSE,
            associated_data=aad,
            ciphertext=sealed,
        )
        forged_plaintext = transform(plaintext)
        forged = self.provider.seal(
            purpose=space._ROOT_PURPOSE,
            associated_data=aad,
            plaintext=forged_plaintext,
        )
        (root / "k0").write_bytes(forged)

    def test_group_world_access_on_project_root_is_rejected_before_crypto(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            calls = self._provider_open_counter()
            os.chmod(root, 0o750)
            with self.assertRaisesRegex(ObjectSpaceError, "group/world"):
                self.load(root, project, handle)
            self.assertEqual(calls["count"], 0)

    def test_group_world_access_on_k1_is_rejected_before_crypto(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            calls = self._provider_open_counter()
            os.chmod(root / "k1", 0o750)
            with self.assertRaisesRegex(ObjectSpaceError, "group/world"):
                self.load(root, project, handle)
            self.assertEqual(calls["count"], 0)

    def test_group_world_writable_k0_is_rejected_before_crypto(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            calls = self._provider_open_counter()
            os.chmod(root / "k0", 0o666)
            with self.assertRaisesRegex(ObjectSpaceError, "group/world writable"):
                self.load(root, project, handle)
            self.assertEqual(calls["count"], 0)

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_k0_hard_link_alias_is_rejected_before_crypto(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            calls = self._provider_open_counter()
            os.link(root / "k0", Path(temporary) / "k0-alias")
            with self.assertRaisesRegex(ObjectSpaceError, "exactly one filesystem link"):
                self.load(root, project, handle)
            self.assertEqual(calls["count"], 0)

    def test_group_world_writable_authoritative_cell_is_rejected_before_object_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            record = project.records[0]
            os.chmod(root / "k1" / record.locator_text, 0o666)
            calls = self._provider_open_counter()
            with self.assertRaisesRegex(ObjectSpaceError, "group/world writable"):
                self.load(root, project, handle)
            # k0 is authenticated/opened; the rejected object ciphertext never is.
            self.assertEqual(calls["count"], 1)

    def test_oversized_authoritative_cell_is_rejected_before_object_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            record = project.records[0]
            cell = root / "k1" / record.locator_text
            with cell.open("r+b") as stream:
                stream.truncate(space.MAX_SEALED_OBJECT_BYTES + 1)
            calls = self._provider_open_counter()
            with self.assertRaisesRegex(ObjectSpaceError, "byte limit"):
                self.load(root, project, handle)
            self.assertEqual(calls["count"], 1)

    def test_validly_sealed_duplicate_locator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)

            def mutate(plaintext: bytes) -> bytes:
                header = plaintext[:space._HEADER.size]
                fields = space._HEADER.unpack_from(plaintext, 0)
                count, graph_bytes = fields[-2], fields[-1]
                offset = space._HEADER.size
                records = [
                    list(space._RECORD.unpack_from(plaintext, offset + index * space._RECORD.size))
                    for index in range(count)
                ]
                records[1][2] = records[0][2]
                graph = plaintext[offset + count * space._RECORD.size: offset + count * space._RECORD.size + graph_bytes]
                return header + b"".join(space._RECORD.pack(*record) for record in records) + graph

            self._forge_root_plaintext(root, project, mutate)
            with self.assertRaisesRegex(ObjectSpaceError, "duplicate"):
                self.load(root, project, handle)

    def test_validly_sealed_duplicate_object_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)

            def mutate(plaintext: bytes) -> bytes:
                header = plaintext[:space._HEADER.size]
                fields = space._HEADER.unpack_from(plaintext, 0)
                count, graph_bytes = fields[-2], fields[-1]
                offset = space._HEADER.size
                records = [
                    list(space._RECORD.unpack_from(plaintext, offset + index * space._RECORD.size))
                    for index in range(count)
                ]
                records[1][0] = records[0][0]
                graph = plaintext[offset + count * space._RECORD.size: offset + count * space._RECORD.size + graph_bytes]
                return header + b"".join(space._RECORD.pack(*record) for record in records) + graph

            self._forge_root_plaintext(root, project, mutate)
            with self.assertRaisesRegex(ObjectSpaceError, "duplicate"):
                self.load(root, project, handle)

    def test_validly_sealed_root_id_absent_from_records_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)

            def mutate(plaintext: bytes) -> bytes:
                fields = list(space._HEADER.unpack_from(plaintext, 0))
                fields[4] = bytes.fromhex("fe" * 16)
                return space._HEADER.pack(*fields) + plaintext[space._HEADER.size:]

            self._forge_root_plaintext(root, project, mutate)
            with self.assertRaisesRegex(ObjectSpaceError, "root identity is absent"):
                self.load(root, project, handle)

    def test_provider_root_plaintext_expansion_hits_post_open_budget(self) -> None:
        class ExpandingProvider(TestOnlyProvider):
            def open(inner_self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
                if purpose == space._ROOT_PURPOSE:
                    return b"X" * (_MAX_ROOT_PLAINTEXT_V1 + 1)
                return super().open(
                    purpose=purpose,
                    associated_data=associated_data,
                    ciphertext=ciphertext,
                )

        provider = ExpandingProvider()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            # Create with the normal provider, then attack load with same-key expanding provider.
            project, handle = self.create(root)
            provider.key = self.provider.key
            with self.assertRaisesRegex(ObjectSpaceError, "plaintext outside Object Space policy"):
                self.load(root, project, handle, provider=provider)

    def test_provider_object_plaintext_expansion_hits_post_open_budget(self) -> None:
        class ExpandingProvider(TestOnlyProvider):
            def open(inner_self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
                if purpose == space._OBJECT_PURPOSE:
                    return b"X" * (space.MAX_SOURCE_BYTES + 1)
                return super().open(
                    purpose=purpose,
                    associated_data=associated_data,
                    ciphertext=ciphertext,
                )

        provider = ExpandingProvider()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            provider.key = self.provider.key
            with self.assertRaisesRegex(ObjectSpaceError, "plaintext outside Object Space policy"):
                self.load(root, project, handle, provider=provider)


if __name__ == "__main__":
    unittest.main()
