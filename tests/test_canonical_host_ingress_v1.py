from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.canonical_authority_admission_v1 import CanonicalAuthoritySessionV1
from koschei.canonical_host_ingress_v1 import (
    CanonicalHostIngressError,
    bind_host_ingress_v1,
)
from koschei.crypto_agility_v1 import OBJECT_SPACE_PQ1
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from koschei.trust_plane_session_v1 import (
    CanonicalAuthorityTargetV1,
    TrustedBrokerPolicyV1,
)


class TestOnlyProvider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def __init__(self, key: bytes = b"host-ingress-test-provider-key") -> None:
        self.key = key

    def _stream(self, purpose: bytes, associated_data: bytes, size: int) -> bytes:
        return hashlib.shake_256(self.key + purpose + associated_data).digest(size)

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
        stream = self._stream(purpose, associated_data, len(plaintext))
        body = bytes(a ^ b for a, b in zip(plaintext, stream))
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
            raise ValueError("host ingress test authentication failed")
        stream = self._stream(purpose, associated_data, len(body))
        return bytes(a ^ b for a, b in zip(body, stream))


class Broker:
    broker_id = "koschei.test.host-ingress"

    def __init__(self, authority: CanonicalAuthoritySessionV1) -> None:
        self.authority = authority
        self.calls: list[str] = []

    def issue_session(self, *, target, command: str, now=None):
        self.calls.append(command)
        return self.authority


class CanonicalHostIngressV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("aa" * 16)
        self.root_id = bytes.fromhex("11" * 16)
        self.target = CanonicalAuthorityTargetV1(bytes.fromhex("55" * 32))
        self.broker_policy = TrustedBrokerPolicyV1("koschei.test.host-ingress")

    def _fixture(self, root: Path):
        source = b"witness answer 42\nresolve answer\n"
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

    def test_check_only_ingress_cannot_be_confused_into_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project.ks"
            project, _, authority = self._fixture(root)
            broker = Broker(authority)
            ingress = bind_host_ingress_v1(
                target=self.target,
                broker=broker,
                policy=self.broker_policy,
                allow_check=True,
                allow_run=False,
            )
            checked = ingress.execute("check", root, now=self.now)
            self.assertEqual(checked.project_id, project.project_id)
            with self.assertRaises(CanonicalHostIngressError):
                ingress.execute("run", root, now=self.now)
            self.assertEqual(broker.calls, ["check"])

    def test_run_capability_is_explicit_opt_in_and_native_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "legacy-looking.ks"
            _, _, authority = self._fixture(root)
            broker = Broker(authority)
            ingress = bind_host_ingress_v1(
                target=self.target,
                broker=broker,
                policy=self.broker_policy,
                allow_check=False,
                allow_run=True,
            )
            with (
                patch("koschei.modules.load_graph", side_effect=AssertionError("legacy graph reached")),
                patch("koschei.parser.parse", side_effect=AssertionError("legacy parser reached")),
                patch(
                    "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
                    side_effect=AssertionError("legacy Object Space graph reached"),
                ),
            ):
                ran = ingress.execute("run", root, now=self.now)
            self.assertEqual(ran.value.value, 42)
            self.assertEqual(broker.calls, ["run"])

    def test_repr_does_not_expose_target_or_session_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle, authority = self._fixture(root)
            ingress = bind_host_ingress_v1(
                target=self.target,
                broker=Broker(authority),
                policy=self.broker_policy,
            )
            rendered = repr(ingress)
            self.assertIn("target=<opaque>", rendered)
            self.assertIn("broker=<pinned>", rendered)
            self.assertNotIn(self.target.identity.hex(), rendered)
            self.assertNotIn(self.temporal_key.hex(), rendered)
            self.assertNotIn(handle.hex(), rendered)
            self.assertNotIn(self.project_id.hex(), rendered)

    def test_empty_command_scope_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, _, authority = self._fixture(root)
            with self.assertRaises(CanonicalHostIngressError):
                bind_host_ingress_v1(
                    target=self.target,
                    broker=Broker(authority),
                    policy=self.broker_policy,
                    allow_check=False,
                    allow_run=False,
                )


if __name__ == "__main__":
    unittest.main()
