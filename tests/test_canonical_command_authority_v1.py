from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.canonical_authority_admission_v1 import CanonicalAuthoritySessionV1
from koschei.canonical_command_authority_v1 import (
    CanonicalCommandAuthorityError,
    execute_canonical_command_v1,
)
from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy


class TestOnlyProvider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"canonical-command-test-provider-key") -> None:
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
        tag, body = ciphertext[:32], ciphertext[32:]
        expected = hmac.new(
            self.key,
            purpose + b"\x00" + associated_data + b"\x00" + body,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("test provider authentication failed")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(left ^ right for left, right in zip(body, stream))


class CanonicalCommandAuthorityV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.root_id = bytes.fromhex("11" * 16)

    def _fixture(self, root: Path):
        source = (
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        graph_secret = encode_authenticated_frontend_graph_secret(
            project_id=bytes.fromhex("aa" * 16),
            root_object_id=self.root_id,
            objects={self.root_id: source},
            frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
        )
        project, handle = create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects={self.root_id: source},
            root_object_id=self.root_id,
            graph_secret=graph_secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=bytes.fromhex("aa" * 16),
        )
        authority = CanonicalAuthoritySessionV1(
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=project.project_id,
            expected_epoch=project.epoch,
            temporal_policy=self.policy,
        )
        return project, authority

    def test_check_and_run_use_only_native_authority_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "matrix.ks"
            project, authority = self._fixture(root)
            with (
                patch("koschei.modules.load_graph", side_effect=AssertionError("legacy graph reached")),
                patch("koschei.parser.parse", side_effect=AssertionError("legacy parser reached")),
                patch(
                    "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
                    side_effect=AssertionError("legacy Object Space ModuleGraph reached"),
                ),
            ):
                checked = execute_canonical_command_v1(
                    "check", root, authority=authority, now=self.now
                )
                ran = execute_canonical_command_v1(
                    "run", root, authority=authority, now=self.now
                )
            self.assertEqual(checked.command, "check")
            self.assertEqual(checked.project_id, project.project_id)
            self.assertIsNone(checked.value)
            self.assertEqual(ran.command, "run")
            self.assertEqual(ran.value.value, 42)

    def test_unknown_command_fails_closed_before_any_compatibility_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, authority = self._fixture(root)
            with patch("koschei.modules.load_graph", side_effect=AssertionError("fallback reached")):
                with self.assertRaises(CanonicalCommandAuthorityError):
                    execute_canonical_command_v1(
                        "build", root, authority=authority, now=self.now
                    )

    def test_authority_cannot_be_inferred_from_path_or_source_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "looks-like-main.ks"
            self._fixture(root)
            with self.assertRaises(CanonicalCommandAuthorityError):
                execute_canonical_command_v1("check", root, authority=None, now=self.now)  # type: ignore[arg-type]

    def test_result_and_session_repr_are_secret_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, authority = self._fixture(root)
            result = execute_canonical_command_v1(
                "run", root, authority=authority, now=self.now
            )
            rendered = repr(authority) + repr(result)
            self.assertNotIn(self.temporal_key.hex(), rendered)
            self.assertNotIn(authority.temporal_handle.hex(), rendered)
            self.assertNotIn(authority.expected_project_id.hex(), rendered)


if __name__ == "__main__":
    unittest.main()
