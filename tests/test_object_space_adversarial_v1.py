from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1
from koschei import object_space_v1 as space
from koschei.object_space_v1 import (
    ObjectSpaceError,
    create_object_space_project,
    load_object_space_project,
    rotate_object_space_epoch,
)
from koschei.temporal_access_v1 import TemporalAccessError, TemporalAccessPolicy


class TestOnlyProvider:
    """Authenticated reversible attack-harness provider; not production crypto."""

    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"object-space-adversarial-test-provider") -> None:
        self.key = key
        self.before_seal = None

    def _stream(self, purpose: bytes, associated_data: bytes, size: int) -> bytes:
        return hashlib.shake_256(self.key + purpose + associated_data).digest(size)

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
        if self.before_seal is not None:
            self.before_seal(purpose, associated_data, plaintext)
        stream = self._stream(purpose, associated_data, len(plaintext))
        body = bytes(left ^ right for left, right in zip(plaintext, stream))
        tag = hmac.new(
            self.key,
            purpose + b"\x00" + associated_data + b"\x00" + body,
            hashlib.sha256,
        ).digest()
        return tag + body

    def open(self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
        if len(ciphertext) < 32:
            raise ValueError("truncated attack-harness ciphertext")
        tag, body = ciphertext[:32], ciphertext[32:]
        expected = hmac.new(
            self.key,
            purpose + b"\x00" + associated_data + b"\x00" + body,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("attack-harness authentication failed")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(left ^ right for left, right in zip(body, stream))


class ObjectSpaceAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.root_id = bytes.fromhex("11" * 16)
        self.worker_id = bytes.fromhex("22" * 16)
        self.audit_id = bytes.fromhex("33" * 16)
        self.objects = {
            self.root_id: b"ROOT-SECRET-BYTES",
            self.worker_id: b"WORKER-SECRET-BYTES",
            self.audit_id: b"AUDIT-SECRET-BYTES",
        }

    def create(self, root: Path, *, provider=None, project_id=None):
        return create_object_space_project(
            root,
            provider=self.provider if provider is None else provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=b"sealed-secret-topology",
            temporal_policy=self.policy,
            now=self.now,
            project_id=project_id,
        )

    def load(self, root: Path, project, handle, *, provider=None, epoch=None):
        return load_object_space_project(
            root,
            provider=self.provider if provider is None else provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=project.project_id,
            expected_epoch=project.epoch if epoch is None else epoch,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_k0_ciphertext_bitflip_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            payload = bytearray((root / "k0").read_bytes())
            payload[len(payload) // 2] ^= 0x01
            (root / "k0").write_bytes(payload)

            with self.assertRaises(ObjectSpaceError):
                self.load(root, project, handle)

    def test_authoritative_cell_swap_is_rejected_by_context_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            first, second = project.records[:2]
            first_path = root / "k1" / first.locator_text
            second_path = root / "k1" / second.locator_text
            first_bytes = first_path.read_bytes()
            second_bytes = second_path.read_bytes()
            first_path.write_bytes(second_bytes)
            second_path.write_bytes(first_bytes)

            with self.assertRaises(ObjectSpaceError):
                self.load(root, project, handle)

    def test_cross_project_k0_replay_is_rejected_even_with_same_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project_a, _handle_a = self.create(base / "a")
            project_b, handle_b = self.create(base / "b")
            (base / "b" / "k0").write_bytes((base / "a" / "k0").read_bytes())

            self.assertNotEqual(project_a.project_id, project_b.project_id)
            with self.assertRaises(ObjectSpaceError):
                self.load(base / "b", project_b, handle_b)

    def test_one_bit_temporal_handle_forgery_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            forged = bytearray(handle)
            forged[0] ^= 0x80

            with self.assertRaises(TemporalAccessError):
                self.load(root, project, bytes(forged))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_opaque_symlink_decoy_in_k1_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            target = root / "outside"
            target.write_bytes(b"attacker")
            os.symlink(target, root / "k1" / ("ab" * 32))

            with self.assertRaisesRegex(ObjectSpaceError, "non-regular|symlink"):
                self.load(root, project, handle)

    @unittest.skipUnless(hasattr(os, "link"), "hard-link support is required")
    def test_hard_link_alias_in_k1_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            authoritative = root / "k1" / project.records[0].locator_text
            alias = root / "k1" / ("cd" * 32)
            os.link(authoritative, alias)

            with self.assertRaisesRegex(ObjectSpaceError, "exactly one filesystem link"):
                self.load(root, project, handle)

    def test_noncanonical_but_validly_sealed_k0_record_order_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            sealed = (root / "k0").read_bytes()
            aad = space._root_aad(project.project_id, project.epoch)
            plaintext = self.provider.open(
                purpose=space._ROOT_PURPOSE,
                associated_data=aad,
                ciphertext=sealed,
            )
            header = plaintext[: space._HEADER.size]
            fields = space._HEADER.unpack_from(plaintext, 0)
            object_count = fields[-2]
            graph_bytes = fields[-1]
            self.assertGreaterEqual(object_count, 2)
            offset = space._HEADER.size
            records = [
                plaintext[
                    offset + index * space._RECORD.size :
                    offset + (index + 1) * space._RECORD.size
                ]
                for index in range(object_count)
            ]
            graph = plaintext[
                offset + object_count * space._RECORD.size :
                offset + object_count * space._RECORD.size + graph_bytes
            ]
            forged_plaintext = header + b"".join(reversed(records)) + graph
            forged = self.provider.seal(
                purpose=space._ROOT_PURPOSE,
                associated_data=aad,
                plaintext=forged_plaintext,
            )
            (root / "k0").write_bytes(forged)

            with self.assertRaisesRegex(ObjectSpaceError, "not canonical"):
                self.load(root, project, handle)

    def test_concurrent_same_epoch_rotations_only_one_can_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            barrier = threading.Barrier(3)
            successes: list[int] = []
            failures: list[Exception] = []
            lock = threading.Lock()

            def worker() -> None:
                barrier.wait()
                try:
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
                    with lock:
                        successes.append(rotated.epoch)
                except Exception as error:  # attack outcome is intentionally broad.
                    with lock:
                        failures.append(error)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(successes, [2])
            self.assertEqual(len(failures), 1)

    def test_root_path_swap_before_commit_cannot_redirect_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            moved = base / "admitted-project"
            project, handle = self.create(root)
            original_k0 = (root / "k0").read_bytes()
            fired = False

            def swap_on_rotation_object(purpose, _aad, _plaintext) -> None:
                nonlocal fired
                if fired or purpose != space._OBJECT_PURPOSE:
                    return
                fired = True
                os.rename(root, moved)
                root.mkdir(mode=0o700)
                (root / "k1").mkdir(mode=0o700)
                (root / "k0").write_bytes(b"ATTACKER-REPLACEMENT")

            self.provider.before_seal = swap_on_rotation_object
            with self.assertRaisesRegex(ObjectSpaceError, "path identity changed"):
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

            self.assertEqual((moved / "k0").read_bytes(), original_k0)
            self.assertEqual((root / "k0").read_bytes(), b"ATTACKER-REPLACEMENT")
            loaded = self.load(moved, project, handle)
            self.assertEqual(loaded.epoch, 1)
            self.assertEqual(loaded.object_payloads, project.object_payloads)

    def test_pre_switch_rename_failure_rolls_back_new_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            before_names = set(os.listdir(root / "k1"))
            before_k0 = (root / "k0").read_bytes()

            with patch(
                "koschei.object_space_adversarial_guard_v1.os.rename",
                side_effect=OSError("injected rename failure"),
            ):
                with self.assertRaises(OSError):
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

            self.assertEqual((root / "k0").read_bytes(), before_k0)
            self.assertEqual(set(os.listdir(root / "k1")), before_names)
            loaded = self.load(root, project, handle)
            self.assertEqual(loaded.epoch, 1)

    def test_post_switch_cleanup_failure_leaves_only_inert_old_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            old_names = {record.locator_text for record in project.records}

            with patch(
                "koschei.object_space_adversarial_guard_v1._space._unlink_at",
                side_effect=OSError("injected cleanup failure"),
            ):
                rotated, new_handle = rotate_object_space_epoch(
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
            self.assertTrue(old_names.issubset(set(rotated.unreferenced_locators)))
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=new_handle,
                expected_project_id=project.project_id,
                expected_epoch=2,
                temporal_policy=self.policy,
                now=self.now,
            )
            self.assertEqual(loaded.object_payloads, project.object_payloads)
            self.assertTrue(old_names.issubset(set(loaded.unreferenced_locators)))


if __name__ == "__main__":
    unittest.main()
