from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import koschei.object_space_frontend_identity_v1 as frontend
from koschei.native_kernel_v1 import NativeKernelError
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    ObjectSpaceFrontendIdentityError,
    check_object_space_graph_by_authenticated_frontend,
    decode_authenticated_frontend_graph,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_graph_v1 import ObjectSpaceGraphError, encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class AuthenticatedFrontendIdentityAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("91" * 16)
        self.root_id = bytes.fromhex("a2" * 16)
        self.native_source = b"witness answer 7\nresolve answer\n"
        self.objects = {self.root_id: self.native_source}
        self.secret = encode_authenticated_frontend_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )[0]

    def test_native_identity_with_legacy_source_is_rejected_without_fallback(self) -> None:
        legacy_source = b"fn main() { return 7 }\n"
        with patch(
            "koschei.object_space_graph_v1.parse",
            side_effect=AssertionError("legacy parser must not be attempted"),
        ):
            with self.assertRaises(NativeKernelError):
                encode_authenticated_frontend_graph_secret(
                    project_id=self.project_id,
                    root_object_id=self.root_id,
                    objects={self.root_id: legacy_source},
                    frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
                )

    def test_unknown_frontend_identity_is_rejected_before_source_execution(self) -> None:
        with patch(
            "koschei.object_space_frontend_identity_v1.check_native_kernel",
            side_effect=AssertionError("source should not execute"),
        ):
            with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "unsupported"):
                encode_authenticated_frontend_graph_secret(
                    project_id=self.project_id,
                    root_object_id=self.root_id,
                    objects=self.objects,
                    frontend_by_object={self.root_id: bytes.fromhex("ef" * 32)},
                )

    def test_frontend_binding_set_must_exactly_match_object_authority(self) -> None:
        other = bytes.fromhex("b3" * 16)
        with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "exactly match"):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=self.objects,
                frontend_by_object={},
            )
        with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "exactly match"):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=self.objects,
                frontend_by_object={
                    self.root_id: NATIVE_WITNESS_FRONTEND_V1,
                    other: NATIVE_WITNESS_FRONTEND_V1,
                },
            )

    def test_multi_object_native_project_is_rejected_until_relationship_semantics_exist(self) -> None:
        other = bytes.fromhex("b4" * 16)
        objects = {
            self.root_id: self.native_source,
            other: b"witness other 3\nresolve other\n",
        }
        with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "exactly one"):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=objects,
                frontend_by_object={
                    self.root_id: NATIVE_WITNESS_FRONTEND_V1,
                    other: NATIVE_WITNESS_FRONTEND_V1,
                },
            )

    def test_root_must_be_authoritative_object(self) -> None:
        missing = bytes.fromhex("c5" * 16)
        with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "root object is absent"):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=missing,
                objects=self.objects,
                frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
            )

    def test_tampered_frontend_identity_in_sealed_graph_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "reality")
            payload = bytearray(project.graph_secret)
            frontend_offset = frontend._HEADER.size + 16 + 32
            payload[frontend_offset : frontend_offset + 32] = bytes.fromhex("dd" * 32)
            forged = replace(project, graph_secret=bytes(payload))
            with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "unsupported"):
                decode_authenticated_frontend_graph(forged)

    def test_count_and_length_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "reality")
            truncated = replace(project, graph_secret=project.graph_secret[:-1])
            with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "length"):
                decode_authenticated_frontend_graph(truncated)

            payload = bytearray(project.graph_secret)
            # object_count is the final uint32 in the 64-byte v1 header.
            payload[56:60] = (2).to_bytes(4, "big")
            forged = replace(project, graph_secret=bytes(payload))
            with self.assertRaises(ObjectSpaceFrontendIdentityError):
                decode_authenticated_frontend_graph(forged)

    def test_digest_tamper_against_k0_authority_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "reality")
            payload = bytearray(project.graph_secret)
            digest_offset = frontend._HEADER.size + 16
            payload[digest_offset : digest_offset + 32] = bytes.fromhex("ab" * 32)
            forged = replace(project, graph_secret=bytes(payload))
            with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "k0 authority"):
                decode_authenticated_frontend_graph(forged)

    def test_valid_native_schema_with_malformed_native_source_never_tries_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "reality")
            malformed = b"fn main() { return 9 }\n"
            digest = hashlib.sha256(malformed).digest()

            body = bytearray(
                frontend._HEADER.pack(
                    frontend.FRONTEND_GRAPH_MAGIC_V1,
                    frontend.FRONTEND_GRAPH_VERSION_V1,
                    self.project_id,
                    self.root_id,
                    1,
                )
            )
            body.extend(
                frontend._OBJECT.pack(
                    self.root_id,
                    digest,
                    NATIVE_WITNESS_FRONTEND_V1,
                )
            )
            records = tuple(
                replace(record, artifact_digest=digest)
                for record in project.records
            )
            forged = replace(
                project,
                graph_secret=bytes(body),
                records=records,
                object_payloads={self.root_id: malformed},
            )
            with patch(
                "koschei.object_space_graph_v1.parse",
                side_effect=AssertionError("legacy fallback reached"),
            ):
                with self.assertRaises(NativeKernelError):
                    check_object_space_graph_by_authenticated_frontend(forged)

    def test_legacy_schema_with_native_looking_source_does_not_auto_upgrade(self) -> None:
        with self.assertRaises((ObjectSpaceGraphError, NativeKernelError, Exception)) as caught:
            encode_object_space_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=self.objects,
                target_by_import_slot={},
            )
        # The legacy encoder/parser owns the legacy schema path. It must not turn
        # native-looking bytes into authenticated native metadata automatically.
        self.assertNotIsInstance(caught.exception, AssertionError)

    def test_magic_tamper_does_not_trigger_source_sniffing_native_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.create(Path(temporary) / "reality")
            payload = bytearray(project.graph_secret)
            payload[0] ^= 0x01
            forged = replace(project, graph_secret=bytes(payload))
            # Dispatcher sees no valid native schema marker and delegates to the
            # explicit legacy schema decoder. That decoder must fail schema before
            # parsing the native-looking source.
            with patch(
                "koschei.object_space_graph_v1.parse",
                side_effect=AssertionError("source sniffing occurred"),
            ):
                with self.assertRaises(ObjectSpaceGraphError):
                    check_object_space_graph_by_authenticated_frontend(forged)


if __name__ == "__main__":
    unittest.main()
