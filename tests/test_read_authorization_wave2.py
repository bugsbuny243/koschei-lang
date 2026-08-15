from __future__ import annotations

import dataclasses
import unittest

from koschei.decoy_view_broker_v1 import require_canonical_build_view
from koschei.read_authorization_v1 import (
    ReadAuthorizationError,
    issue_read_grant,
    read_with_grant,
    verify_read_grant,
)


OID = "0123456789abcdef0123456789abcdef"
OTHER_OID = "fedcba9876543210fedcba9876543210"
AUTH_KEY = b"a" * 32
DECEPTION_KEY = b"d" * 32
BUILD_VIEW_KEY = b"b" * 32
CANONICAL = b"fn protected_value() -> Int { return 777777; }\n"


class ReadAuthorizationWave2Tests(unittest.TestCase):
    def grant(self):
        return issue_read_grant(
            project_id="p-01",
            object_id=OID,
            not_before_epoch=100,
            expires_after_epoch=102,
            nonce="nonce-000000000001",
            authorization_key=AUTH_KEY,
        )

    def test_valid_short_lived_grant_reaches_canonical_reader(self):
        calls = []
        view = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=self.grant(),
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
        )
        self.assertEqual(calls, [OID])
        self.assertEqual(view.provenance, "canonical")
        self.assertEqual(view.content, CANONICAL)

    def test_valid_grant_can_produce_cryptographically_attested_build_view(self):
        view = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=self.grant(),
            canonical_reader=lambda _: CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
            canonical_view_key=BUILD_VIEW_KEY,
        )
        require_canonical_build_view(view, canonical_view_key=BUILD_VIEW_KEY)

    def test_mac_bit_flip_falls_to_decoy_without_canonical_read(self):
        grant = self.grant()
        flipped = dataclasses.replace(grant, mac=("0" if grant.mac[0] != "0" else "1") + grant.mac[1:])
        calls = []
        view = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=flipped,
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
        )
        self.assertEqual(calls, [])
        self.assertEqual(view.provenance, "decoy")
        self.assertNotIn(b"777777", view.content)

    def test_wrong_object_id_cannot_reuse_grant(self):
        calls = []
        view = read_with_grant(
            project_id="p-01", object_id=OTHER_OID, epoch=101, grant=self.grant(),
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
        )
        self.assertEqual(calls, [])
        self.assertEqual(view.provenance, "decoy")

    def test_stale_epoch_replay_falls_to_rotated_decoy(self):
        grant = self.grant()
        calls = []
        stale = read_with_grant(
            project_id="p-01", object_id=OID, epoch=103, grant=grant,
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
        )
        later = read_with_grant(
            project_id="p-01", object_id=OID, epoch=104, grant=grant,
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=AUTH_KEY,
        )
        self.assertEqual(calls, [])
        self.assertEqual(stale.provenance, "decoy")
        self.assertEqual(later.provenance, "decoy")
        self.assertNotEqual(stale.content, later.content)

    def test_authorization_key_rotation_invalidates_old_grant(self):
        calls = []
        view = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=self.grant(),
            canonical_reader=lambda oid: calls.append(oid) or CANONICAL,
            deception_key=DECEPTION_KEY, authorization_key=b"b" * 32,
        )
        self.assertEqual(calls, [])
        self.assertEqual(view.provenance, "decoy")

    def test_deception_key_rotation_changes_unauthorized_universe(self):
        bad_grant = dataclasses.replace(self.grant(), mac="f" * 64)
        one = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=bad_grant,
            canonical_reader=lambda _: CANONICAL,
            deception_key=b"x" * 32, authorization_key=AUTH_KEY,
        )
        two = read_with_grant(
            project_id="p-01", object_id=OID, epoch=101, grant=bad_grant,
            canonical_reader=lambda _: CANONICAL,
            deception_key=b"y" * 32, authorization_key=AUTH_KEY,
        )
        self.assertEqual(one.provenance, "decoy")
        self.assertEqual(two.provenance, "decoy")
        self.assertNotEqual(one.content, two.content)

    def test_malformed_public_grant_fails_closed_instead_of_throwing_type_error(self):
        malformed = dataclasses.replace(self.grant(), not_before_epoch="100")
        self.assertFalse(
            verify_read_grant(
                malformed,
                project_id="p-01",
                object_id=OID,
                epoch=101,
                authorization_key=AUTH_KEY,
            )
        )

    def test_malformed_mac_type_fails_closed(self):
        malformed = dataclasses.replace(self.grant(), mac=b"x" * 32)
        self.assertFalse(
            verify_read_grant(
                malformed,
                project_id="p-01",
                object_id=OID,
                epoch=101,
                authorization_key=AUTH_KEY,
            )
        )

    def test_nul_delimited_grant_fields_are_rejected(self):
        with self.assertRaises(ReadAuthorizationError):
            issue_read_grant(
                project_id="p-01\x00shadow",
                object_id=OID,
                not_before_epoch=100,
                expires_after_epoch=102,
                nonce="nonce-000000000001",
                authorization_key=AUTH_KEY,
            )
        with self.assertRaises(ReadAuthorizationError):
            issue_read_grant(
                project_id="p-01",
                object_id=OID,
                not_before_epoch=100,
                expires_after_epoch=102,
                nonce="nonce-000000000001\x00shadow",
                authorization_key=AUTH_KEY,
            )


if __name__ == "__main__":
    unittest.main()
