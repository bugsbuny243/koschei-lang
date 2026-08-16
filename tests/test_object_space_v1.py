from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import tempfile
import unittest

from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1, CryptoAgilityError
from koschei.object_space_v1 import (
    OBJECT_STORE_NAME,
    ROOT_CAPSULE_NAME,
    ObjectSpaceError,
    create_object_space_project,
    load_object_space_project,
    rotate_object_space_epoch,
)
from koschei.temporal_access_v1 import TemporalAccessError, TemporalAccessPolicy


class TestOnlyProvider:
    """Authenticated reversible test provider; never shipped as production crypto."""

    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"test-only-object-space-provider-key") -> None:
        self.key = key

    def _stream(self, purpose: bytes, associated_data: bytes, size: int) -> bytes:
        return hashlib.shake_256(self.key + purpose + associated_data).digest(size)

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
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
            raise ValueError("truncated test ciphertext")
        tag, body = ciphertext[:32], ciphertext[32:]
        expected = hmac.new(
            self.key,
            purpose + b"\x00" + associated_data + b"\x00" + body,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("test ciphertext authentication failed")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(left ^ right for left, right in zip(body, stream))


class WrongProfileProvider(TestOnlyProvider):
    profile_id = "wrong-profile"


class ObjectSpaceV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.root_id = bytes.fromhex("11" * 16)
        self.worker_id = bytes.fromhex("22" * 16)
        self.objects = {
            self.root_id: b"PAYMENT_ROOT_SECRET_SOURCE",
            self.worker_id: b"AUTH_RISK_WORKER_SECRET_SOURCE",
        }
        self.graph_secret = b"payment-root -> auth-risk-worker"
        self.now = 1_800_000_000

    def create(self, directory: Path):
        return create_object_space_project(
            directory,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.graph_secret,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_canonical_filesystem_surface_is_only_k0_k1_and_opaque_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, _ = self.create(root)

            self.assertEqual(sorted(item.name for item in root.iterdir()), ["k0", "k1"])
            self.assertTrue((root / ROOT_CAPSULE_NAME).is_file())
            self.assertTrue((root / OBJECT_STORE_NAME).is_dir())
            names = sorted(item.name for item in (root / OBJECT_STORE_NAME).iterdir())
            self.assertEqual(len(names), 2)
            self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", name) for name in names))
            self.assertEqual({record.locator_text for record in project.records}, set(names))
            self.assertFalse(any("payment" in name or "auth" in name for name in names))
            self.assertFalse(any("." in name for name in names))

    def test_plaintext_source_and_graph_roles_do_not_appear_in_project_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            self.create(root)
            raw = (root / "k0").read_bytes()
            for cell in (root / "k1").iterdir():
                raw += cell.read_bytes()

            self.assertNotIn(b"PAYMENT_ROOT_SECRET_SOURCE", raw)
            self.assertNotIn(b"AUTH_RISK_WORKER_SECRET_SOURCE", raw)
            self.assertNotIn(self.graph_secret, raw)
            self.assertNotIn(self.root_id, raw)
            self.assertNotIn(self.worker_id, raw)

    def test_temporal_handle_expires_at_next_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)

            load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=project.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now + 29,
            )
            with self.assertRaises(TemporalAccessError):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now + 30,
                )

    def test_temporal_handle_is_bound_to_project_and_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            wrong_project = bytes.fromhex("99" * 16)

            with self.assertRaises(TemporalAccessError):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=wrong_project,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )
            with self.assertRaises(TemporalAccessError):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=2,
                    temporal_policy=self.policy,
                    now=self.now,
                )

    def test_epoch_rotation_changes_every_physical_locator_and_invalidates_old_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            before, old_handle = self.create(root)
            old_locators = {record.locator_text for record in before.records}

            after, new_handle = rotate_object_space_epoch(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=old_handle,
                expected_project_id=before.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            new_locators = {record.locator_text for record in after.records}

            self.assertEqual(after.epoch, 2)
            self.assertEqual(after.project_id, before.project_id)
            self.assertEqual(after.root_object_id, before.root_object_id)
            self.assertEqual(after.object_payloads, before.object_payloads)
            self.assertTrue(old_locators.isdisjoint(new_locators))
            self.assertNotEqual(old_handle, new_handle)
            with self.assertRaises(TemporalAccessError):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=old_handle,
                    expected_project_id=before.project_id,
                    expected_epoch=2,
                    temporal_policy=self.policy,
                    now=self.now,
                )
            with self.assertRaises((ObjectSpaceError, TemporalAccessError)):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=old_handle,
                    expected_project_id=before.project_id,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )

    def test_unreferenced_opaque_cell_is_inert_not_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            decoy = "ab" * 32
            (root / "k1" / decoy).write_bytes(b"not-authoritative")

            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=project.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            self.assertEqual(loaded.object_payloads, project.object_payloads)
            self.assertEqual(loaded.unreferenced_locators, (decoy,))

    def test_nonopaque_name_in_k1_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project, handle = self.create(root)
            (root / "k1" / "payment.ks").write_bytes(b"attacker")

            with self.assertRaisesRegex(ObjectSpaceError, "non-opaque"):
                load_object_space_project(
                    root,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )

    def test_provider_profile_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            with self.assertRaises(CryptoAgilityError):
                create_object_space_project(
                    root,
                    provider=WrongProfileProvider(),
                    temporal_key=self.temporal_key,
                    objects=self.objects,
                    root_object_id=self.root_id,
                    temporal_policy=self.policy,
                    now=self.now,
                )


if __name__ == "__main__":
    unittest.main()
