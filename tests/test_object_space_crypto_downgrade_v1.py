from __future__ import annotations

import unittest

from koschei.crypto_agility_v1 import (
    OBJECT_SPACE_PQ1,
    CryptoAgilityError,
    CryptoProfileV1,
    require_profile,
)


class ClaimingProvider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
        return b"x" + plaintext

    def open(self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
        return ciphertext[1:]


class ObjectSpaceCryptoDowngradeV1Tests(unittest.TestCase):
    def test_same_registered_id_cannot_change_algorithm_contract(self) -> None:
        downgraded = CryptoProfileV1(
            profile_id="koschei-pq1",
            at_rest_aead="WEAK-AEAD",
            key_establishment="ML-KEM-1024",
            primary_signature="ML-DSA-87",
            backup_signature="SLH-DSA",
            digest="SHA3-512",
        )
        with self.assertRaisesRegex(CryptoAgilityError, "downgrade|mutation"):
            require_profile(ClaimingProvider(), downgraded)

    def test_unregistered_profile_id_is_not_silently_accepted(self) -> None:
        unknown = CryptoProfileV1(
            profile_id="koschei-pq2",
            at_rest_aead="AES-256-GCM",
            key_establishment="ML-KEM-1024",
            primary_signature="ML-DSA-87",
            backup_signature="SLH-DSA",
            digest="SHA3-512",
        )
        provider = ClaimingProvider()
        provider.profile_id = "koschei-pq2"
        with self.assertRaisesRegex(CryptoAgilityError, "unregistered"):
            require_profile(provider, unknown)

    def test_profile_serialization_tokens_cannot_contain_separator_injection(self) -> None:
        malformed = CryptoProfileV1(
            profile_id="koschei-pq1",
            at_rest_aead="AES-256-GCM\x00ML-KEM-1024",
            key_establishment="ML-KEM-1024",
            primary_signature="ML-DSA-87",
            backup_signature="SLH-DSA",
            digest="SHA3-512",
        )
        with self.assertRaisesRegex(CryptoAgilityError, "canonical"):
            require_profile(ClaimingProvider(), malformed)


if __name__ == "__main__":
    unittest.main()
