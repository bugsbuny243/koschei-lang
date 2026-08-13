from __future__ import annotations

import hashlib
import hmac
import unittest

from koschei.commercial_entitlement_v1 import (
    ArtifactIdentity,
    EntitlementClaims,
    canonical_entitlement_payload,
    entitlement_digest,
    verify_entitlement,
)


class CommercialEntitlementV1Tests(unittest.TestCase):
    def setUp(self):
        self.artifact = ArtifactIdentity(
            product="koschei-secure-runtime",
            version="0.10.0",
            artifact_sha256="a" * 64,
            policy_hash="b" * 64,
            channel="enterprise",
        )
        self.claims = EntitlementClaims(
            customer_id="customer-001",
            edition="enterprise",
            seats=25,
            features=("secure-runtime", "deception-plane"),
            not_before_epoch=100,
            expires_after_epoch=200,
            artifact=self.artifact,
        )
        self.test_key = b"test-only-entitlement-key-32bytes!!"

    def _sign(self, payload: bytes) -> bytes:
        return hmac.new(self.test_key, payload, hashlib.sha256).digest()

    def _verify(self, payload: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self._sign(payload), signature)

    def test_payload_is_deterministic_and_order_independent_for_features(self):
        first = canonical_entitlement_payload(self.claims)
        reordered = EntitlementClaims(
            customer_id=self.claims.customer_id,
            edition=self.claims.edition,
            seats=self.claims.seats,
            features=("deception-plane", "secure-runtime", "secure-runtime"),
            not_before_epoch=self.claims.not_before_epoch,
            expires_after_epoch=self.claims.expires_after_epoch,
            artifact=self.artifact,
        )
        self.assertEqual(first, canonical_entitlement_payload(reordered))
        self.assertEqual(entitlement_digest(self.claims), hashlib.sha256(first).hexdigest())

    def test_valid_entitlement_binds_artifact_policy_epoch_and_feature(self):
        payload = canonical_entitlement_payload(self.claims)
        signature = self._sign(payload)
        self.assertTrue(verify_entitlement(
            claims=self.claims,
            signature=signature,
            verifier=self._verify,
            current_epoch=150,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="b" * 64,
            required_feature="deception-plane",
        ))

    def test_tampered_signature_fails_closed(self):
        signature = bytearray(self._sign(canonical_entitlement_payload(self.claims)))
        signature[0] ^= 1
        self.assertFalse(verify_entitlement(
            claims=self.claims,
            signature=bytes(signature),
            verifier=self._verify,
            current_epoch=150,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="b" * 64,
        ))

    def test_wrong_artifact_or_policy_fails_closed(self):
        signature = self._sign(canonical_entitlement_payload(self.claims))
        self.assertFalse(verify_entitlement(
            claims=self.claims,
            signature=signature,
            verifier=self._verify,
            current_epoch=150,
            expected_artifact_sha256="c" * 64,
            expected_policy_hash="b" * 64,
        ))
        self.assertFalse(verify_entitlement(
            claims=self.claims,
            signature=signature,
            verifier=self._verify,
            current_epoch=150,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="c" * 64,
        ))

    def test_expired_or_missing_feature_fails_closed(self):
        signature = self._sign(canonical_entitlement_payload(self.claims))
        self.assertFalse(verify_entitlement(
            claims=self.claims,
            signature=signature,
            verifier=self._verify,
            current_epoch=201,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="b" * 64,
        ))
        self.assertFalse(verify_entitlement(
            claims=self.claims,
            signature=signature,
            verifier=self._verify,
            current_epoch=150,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="b" * 64,
            required_feature="sentinel-enterprise",
        ))


if __name__ == "__main__":
    unittest.main()
