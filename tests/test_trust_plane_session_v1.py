from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.canonical_authority_admission_v1 import CanonicalAuthoritySessionV1
from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from koschei.trust_plane_session_v1 import (
    CanonicalAuthorityTargetV1,
    TrustPlaneSessionError,
    TrustedBrokerPolicyV1,
    execute_with_trusted_broker_v1,
)


class TestOnlyProvider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"trust-plane-test-provider-key") -> None:
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
            raise ValueError("BROKER_SECRET_PROVIDER_DETAIL")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(left ^ right for left, right in zip(body, stream))


class Broker:
    broker_id = "koschei.test.trust-plane-v1"

    def __init__(self, authority: CanonicalAuthoritySessionV1) -> None:
        self.authority = authority
        self.calls: list[tuple[bytes, str]] = []

    def issue_session(self, *, target, command: str, now=None):
        self.calls.append((target.identity, command))
        return self.authority


class ExplodingBroker(Broker):
    def issue_session(self, *, target, command: str, now=None):
        raise RuntimeError("BROKER_INTERNAL_SECRET_DETAIL")


class TrustPlaneSessionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("aa" * 16)
        self.root_id = bytes.fromhex("11" * 16)
        self.target = CanonicalAuthorityTargetV1(bytes.fromhex("77" * 32))
        self.broker_policy = TrustedBrokerPolicyV1("koschei.test.trust-plane-v1")

    def _fixture(self, root: Path):
        source = (
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        graph_secret = encode_authenticated_frontend_graph_secret(
            project_id=self.project_id,
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
            project_id=self.project_id,
        )
        authority = CanonicalAuthoritySessionV1(
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=project.project_id,
            expected_epoch=project.epoch,
            temporal_policy=self.policy,
        )
        return project, handle, authority

    def test_broker_gateway_runs_native_without_legacy_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "looks-legacy.ks"
            project, _, authority = self._fixture(root)
            broker = Broker(authority)
            with (
                patch("koschei.modules.load_graph", side_effect=AssertionError("legacy graph reached")),
                patch("koschei.parser.parse", side_effect=AssertionError("legacy parser reached")),
                patch(
                    "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
                    side_effect=AssertionError("legacy Object Space graph reached"),
                ),
            ):
                checked = execute_with_trusted_broker_v1(
                    "check",
                    root,
                    target=self.target,
                    broker=broker,
                    policy=self.broker_policy,
                    now=self.now,
                )
                ran = execute_with_trusted_broker_v1(
                    "run",
                    root,
                    target=self.target,
                    broker=broker,
                    policy=self.broker_policy,
                    now=self.now,
                )
            self.assertEqual(checked.project_id, project.project_id)
            self.assertEqual(ran.value.value, 42)
            self.assertEqual(broker.calls, [(self.target.identity, "check"), (self.target.identity, "run")])

    def test_broker_identity_is_pinned_before_session_issuance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, _, authority = self._fixture(root)
            broker = Broker(authority)
            with self.assertRaises(TrustPlaneSessionError):
                execute_with_trusted_broker_v1(
                    "check",
                    root,
                    target=self.target,
                    broker=broker,
                    policy=TrustedBrokerPolicyV1("different.broker"),
                    now=self.now,
                )
            self.assertEqual(broker.calls, [])

    def test_unknown_command_never_reaches_broker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, _, authority = self._fixture(root)
            broker = Broker(authority)
            with self.assertRaises(TrustPlaneSessionError):
                execute_with_trusted_broker_v1(
                    "build",
                    root,
                    target=self.target,
                    broker=broker,
                    policy=self.broker_policy,
                    now=self.now,
                )
            self.assertEqual(broker.calls, [])

    def test_broker_failure_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle, authority = self._fixture(root)
            with self.assertRaises(TrustPlaneSessionError) as caught:
                execute_with_trusted_broker_v1(
                    "run",
                    root,
                    target=self.target,
                    broker=ExplodingBroker(authority),
                    policy=self.broker_policy,
                    now=self.now,
                )
            text = str(caught.exception)
            self.assertEqual(text, "trusted broker session issuance failed")
            self.assertNotIn("BROKER_INTERNAL_SECRET_DETAIL", text)
            self.assertNotIn(self.temporal_key.hex(), text)
            self.assertNotIn(handle.hex(), text)

    def test_target_repr_is_opaque(self) -> None:
        text = repr(self.target)
        self.assertEqual(text, "CanonicalAuthorityTargetV1(identity=<opaque>)")
        self.assertNotIn(self.target.identity.hex(), text)


if __name__ == "__main__":
    unittest.main()
