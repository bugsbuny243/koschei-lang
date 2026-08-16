from __future__ import annotations

import dataclasses
import hashlib
import unittest

from koschei.decoy_view_broker_v1 import (
    DecoyViewError,
    SourceView,
    generate_decoy_source,
    read_source_view,
    require_canonical_build_view,
)
from koschei.parser import parse


OID = "0123456789abcdef0123456789abcdef"
OTHER_OID = "fedcba9876543210fedcba9876543210"
KEY = b"d" * 32
BUILD_VIEW_KEY = b"b" * 32
SECRET_SOURCE = b"fn vault_secret() -> Int { return 424242; }\n"


def require_current_build_view(view, *, key: bytes = BUILD_VIEW_KEY) -> None:
    require_canonical_build_view(
        view,
        canonical_view_key=key,
        expected_project_id="p-01",
        expected_object_id=OID,
        expected_epoch=500,
    )


class DecoyViewBrokerV1Tests(unittest.TestCase):
    def test_unauthorized_read_never_touches_canonical_reader(self):
        calls = []

        def canonical_reader(object_id: str) -> bytes:
            calls.append(object_id)
            raise AssertionError("canonical reader must not be reached")

        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=False,
            canonical_reader=canonical_reader,
            deception_key=KEY,
        )
        self.assertEqual(calls, [])
        self.assertEqual(view.provenance, "decoy")
        self.assertFalse(view.deployable)
        self.assertNotIn(b"vault_secret", view.content)
        self.assertNotIn(b"424242", view.content)

    def test_authorized_read_returns_canonical_bytes(self):
        calls = []

        def canonical_reader(object_id: str) -> bytes:
            calls.append(object_id)
            return SECRET_SOURCE

        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=canonical_reader,
            deception_key=KEY,
        )
        self.assertEqual(calls, [OID])
        self.assertEqual(view.content, SECRET_SOURCE)
        self.assertEqual(view.provenance, "canonical")
        self.assertTrue(view.deployable)
        self.assertEqual(view.canonical_attestation, "")

    def test_same_epoch_is_stable_and_next_epoch_rotates(self):
        first = generate_decoy_source(project_id="p-01", object_id=OID, epoch=10, deception_key=KEY)
        again = generate_decoy_source(project_id="p-01", object_id=OID, epoch=10, deception_key=KEY)
        next_epoch = generate_decoy_source(project_id="p-01", object_id=OID, epoch=11, deception_key=KEY)
        self.assertEqual(first, again)
        self.assertNotEqual(first, next_epoch)

    def test_decoy_is_valid_current_koschei_syntax(self):
        source = generate_decoy_source(project_id="p-01", object_id=OID, epoch=10, deception_key=KEY)
        program = parse(source.decode("utf-8"))
        self.assertGreaterEqual(len(program.declarations), 2)

    def test_decoy_cannot_enter_build_sign_deploy(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=False,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_canonical_build_view(view, canonical_view_key=BUILD_VIEW_KEY)

    def test_canonical_view_passes_build_gate_only_with_attestation_and_context(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        self.assertTrue(view.canonical_attestation.startswith("hmac-sha256:"))
        require_current_build_view(view)

    def test_unattested_canonical_view_fails_build_gate(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(view)

    def test_public_dataclass_forgery_cannot_enter_build_gate(self):
        digest = "sha256:" + hashlib.sha256(SECRET_SOURCE).hexdigest()
        forged = SourceView(
            object_id=OID,
            epoch=500,
            provenance="canonical",
            deployable=True,
            content=SECRET_SOURCE,
            view_digest=digest,
            project_id="p-01",
            canonical_attestation="hmac-sha256:" + ("0" * 64),
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(forged)

    def test_attested_content_tamper_fails_build_gate(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        tampered = dataclasses.replace(
            view,
            content=b"fn vault_secret() -> Int { return 1; }\n",
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(tampered)

    def test_wrong_build_view_key_fails_closed(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(view, key=b"c" * 32)

    def test_missing_expected_context_fails_closed(self):
        view = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_canonical_build_view(view, canonical_view_key=BUILD_VIEW_KEY)

    def test_old_epoch_attestation_cannot_replay_into_current_build(self):
        stale = read_source_view(
            project_id="p-01",
            object_id=OID,
            epoch=499,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(stale)

    def test_cross_project_and_cross_object_attestations_cannot_replay(self):
        wrong_project = read_source_view(
            project_id="p-shadow",
            object_id=OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        wrong_object = read_source_view(
            project_id="p-01",
            object_id=OTHER_OID,
            epoch=500,
            authorized=True,
            canonical_reader=lambda _: SECRET_SOURCE,
            deception_key=KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        with self.assertRaises(DecoyViewError):
            require_current_build_view(wrong_project)
        with self.assertRaises(DecoyViewError):
            require_current_build_view(wrong_object)

    def test_weak_deception_key_fails_closed(self):
        with self.assertRaises(DecoyViewError):
            generate_decoy_source(project_id="p-01", object_id=OID, epoch=1, deception_key=b"short")

    def test_weak_build_view_key_fails_closed(self):
        with self.assertRaises(DecoyViewError):
            read_source_view(
                project_id="p-01",
                object_id=OID,
                epoch=1,
                authorized=True,
                canonical_reader=lambda _: SECRET_SOURCE,
                deception_key=KEY,
                canonical_view_key=b"short",
            )


if __name__ == "__main__":
    unittest.main()
