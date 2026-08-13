import hashlib
import hmac
import unittest

from koschei.commercial_activation_v1 import (
    ActivationLease,
    canonical_activation_payload,
    device_binding_digest,
    verify_activation,
)
from koschei.commercial_entitlement_v1 import (
    ArtifactIdentity,
    EntitlementClaims,
    canonical_entitlement_payload,
    entitlement_digest,
)


class CommercialActivationV1Tests(unittest.TestCase):
    def setUp(self):
        self.entitlement_key = b"e" * 32
        self.lease_key = b"l" * 32
        self.artifact = ArtifactIdentity(
            product="koschei-lang",
            version="0.10.0",
            artifact_sha256="a" * 64,
            policy_hash="b" * 64,
            channel="private-stable",
        )
        self.entitlement = EntitlementClaims(
            customer_id="cust-001",
            edition="enterprise",
            seats=3,
            features=("compiler", "deception"),
            not_before_epoch=100,
            expires_after_epoch=1000,
            artifact=self.artifact,
        )
        self.binding = device_binding_digest(customer_id="cust-001", device_public_id="device-alpha")
        self.lease = ActivationLease(
            lease_id="lease-001",
            customer_id="cust-001",
            entitlement_digest=entitlement_digest(self.entitlement),
            seat_id="seat-01",
            device_binding=self.binding,
            issued_epoch=120,
            online_until_epoch=200,
            offline_grace_until_epoch=230,
            channel="private-stable",
        )

    def _ent_sig(self):
        return hmac.new(self.entitlement_key, canonical_entitlement_payload(self.entitlement), hashlib.sha256).digest()

    def _lease_sig(self, lease=None):
        lease = lease or self.lease
        return hmac.new(self.lease_key, canonical_activation_payload(lease), hashlib.sha256).digest()

    def _ent_verify(self, payload, sig):
        return hmac.compare_digest(hmac.new(self.entitlement_key, payload, hashlib.sha256).digest(), sig)

    def _lease_verify(self, payload, sig):
        return hmac.compare_digest(hmac.new(self.lease_key, payload, hashlib.sha256).digest(), sig)

    def _verify(self, **overrides):
        kwargs = dict(
            lease=self.lease,
            lease_signature=self._lease_sig(),
            lease_verifier=self._lease_verify,
            entitlement=self.entitlement,
            entitlement_signature=self._ent_sig(),
            entitlement_verifier=self._ent_verify,
            current_epoch=150,
            expected_artifact_sha256="a" * 64,
            expected_policy_hash="b" * 64,
            expected_channel="private-stable",
            expected_device_binding=self.binding,
            required_feature="deception",
        )
        kwargs.update(overrides)
        return verify_activation(**kwargs)

    def test_valid_activation(self):
        self.assertTrue(self._verify())

    def test_wrong_device_fails(self):
        wrong = device_binding_digest(customer_id="cust-001", device_public_id="device-beta")
        self.assertFalse(self._verify(expected_device_binding=wrong))

    def test_revoked_lease_fails(self):
        self.assertFalse(self._verify(revoked_lease_ids={"lease-001"}))

    def test_revoked_seat_fails(self):
        self.assertFalse(self._verify(revoked_seat_ids={"seat-01"}))

    def test_online_expiry_fails_but_offline_grace_can_continue(self):
        self.assertFalse(self._verify(current_epoch=210, online=True))
        self.assertTrue(self._verify(current_epoch=210, online=False))
        self.assertFalse(self._verify(current_epoch=231, online=False))

    def test_wrong_private_channel_fails(self):
        self.assertFalse(self._verify(expected_channel="private-beta"))

    def test_tampered_lease_signature_fails(self):
        self.assertFalse(self._verify(lease_signature=b"tampered"))

    def test_entitlement_binding_mismatch_fails(self):
        altered = EntitlementClaims(
            customer_id=self.entitlement.customer_id,
            edition=self.entitlement.edition,
            seats=self.entitlement.seats,
            features=self.entitlement.features,
            not_before_epoch=self.entitlement.not_before_epoch,
            expires_after_epoch=self.entitlement.expires_after_epoch,
            artifact=ArtifactIdentity(
                product=self.artifact.product,
                version=self.artifact.version,
                artifact_sha256="c" * 64,
                policy_hash=self.artifact.policy_hash,
                channel=self.artifact.channel,
            ),
        )
        self.assertFalse(self._verify(entitlement=altered))


if __name__ == "__main__":
    unittest.main()
