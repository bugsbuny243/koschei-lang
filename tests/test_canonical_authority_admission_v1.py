from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.canonical_authority_admission_v1 import (
    CanonicalAuthorityAdmissionError,
    CanonicalAuthoritySessionV1,
    admit_canonical_object_space_v1,
    check_with_canonical_authority_v1,
    run_with_canonical_authority_v1,
)
from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)


class TestOnlyProvider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"canonical-authority-test-provider-key") -> None:
        self.key = key

    def _stream(self, purpose: bytes, associated_data: bytes, size: int) -> bytes:
        return hashlib.shake_256(self.key + purpose + associated_data).digest(size)

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
        stream = self._stream(purpose, associated_data, len(plaintext))
        body = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(self.key, purpose + b"\0" + associated_data + b"\0" + body, hashlib.sha256).digest()
        return tag + body

    def open(self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
        tag, body = ciphertext[:32], ciphertext[32:]
        expected = hmac.new(self.key, purpose + b"\0" + associated_data + b"\0" + body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("SECRET_PROVIDER_INTERNAL_DETAIL")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(a ^ b for a, b in zip(body, stream))


class WrongProvider(TestOnlyProvider):
    profile_id = "wrong-profile"


class CanonicalAuthorityAdmissionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.project_id = bytes.fromhex("11" * 16)
        self.root_id = bytes.fromhex("22" * 16)
        self.now = 1_800_000_000
        self.source = b"witness base 40\nwitness fee 2\nwitness total sum base fee\nresolve total\n"

    def _create(self, root: Path):
        graph_secret = encode_authenticated_frontend_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: self.source},
            frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
        )
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects={self.root_id: self.source},
            root_object_id=self.root_id,
            graph_secret=graph_secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def _authority(self, handle: bytes, **overrides) -> CanonicalAuthoritySessionV1:
        values = dict(
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=self.project_id,
            expected_epoch=1,
            temporal_policy=self.policy,
        )
        values.update(overrides)
        return CanonicalAuthoritySessionV1(**values)

    def test_admission_then_check_and_run_never_touch_legacy_parser(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "main.ks"
            _, handle = self._create(root)
            authority = self._authority(handle)
            with (
                patch("koschei.modules.load_graph", side_effect=AssertionError("legacy graph reached")),
                patch("koschei.parser.parse", side_effect=AssertionError("legacy parser reached")),
            ):
                checked = check_with_canonical_authority_v1(root, authority=authority, now=self.now)
                ran = run_with_canonical_authority_v1(root, authority=authority, now=self.now)
            self.assertEqual(checked.project_id, self.project_id)
            self.assertEqual(ran.value.value, 42)

    def test_provider_substitution_is_rejected_before_admission(self) -> None:
        with self.assertRaises(CanonicalAuthorityAdmissionError):
            CanonicalAuthoritySessionV1(
                provider=WrongProvider(),
                temporal_key=self.temporal_key,
                temporal_handle=bytes(64),
                expected_project_id=self.project_id,
                expected_epoch=1,
            )

    def test_wrong_project_epoch_or_expired_handle_fail_with_redacted_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            _, handle = self._create(root)
            cases = (
                self._authority(handle, expected_project_id=bytes.fromhex("33" * 16)),
                self._authority(handle, expected_epoch=2),
                self._authority(handle),
            )
            times = (self.now, self.now, self.now + 31)
            for authority, moment in zip(cases, times):
                with self.assertRaises(CanonicalAuthorityAdmissionError) as caught:
                    admit_canonical_object_space_v1(root, authority=authority, now=moment)
                text = str(caught.exception)
                self.assertEqual(text, "canonical Object Space authority admission failed")
                self.assertNotIn(self.temporal_key.hex(), text)
                self.assertNotIn(handle.hex(), text)
                self.assertNotIn("SECRET_PROVIDER_INTERNAL_DETAIL", text)

    def test_authority_repr_redacts_secrets(self) -> None:
        authority = self._authority(bytes.fromhex("aa" * 64))
        text = repr(authority)
        self.assertIn("secrets=<redacted>", text)
        self.assertNotIn(self.temporal_key.hex(), text)
        self.assertNotIn(authority.temporal_handle.hex(), text)
        self.assertNotIn(self.project_id.hex(), text)

    def test_filename_is_not_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "totally-legacy-looking.ks"
            _, handle = self._create(root)
            authority = self._authority(handle)
            project = admit_canonical_object_space_v1(root, authority=authority, now=self.now)
            self.assertEqual(project.root, root.resolve())


if __name__ == "__main__":
    unittest.main()
