from __future__ import annotations

import unittest

from koschei.crypto_agility_v1 import (
    OBJECT_SPACE_PQ1,
    CryptoAgilityError,
    CryptoProfileV1,
    require_profile,
)


class Provider:
    profile_id = OBJECT_SPACE_PQ1.profile_id

    def seal(self, *, purpose: bytes, associated_data: bytes, plaintext: bytes) -> bytes:
        return b"x" + plaintext

    def open(self, *, purpose: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
        return ciphertext[1:]


class CryptoProfileIntegrityV1Tests(unittest.TestCase):
    def test_registered_profile_accepts_exact_canonical_contract(self) -> None:
        provider = Provider()
        self.assertIs(require_profile(provider, OBJECT_SPACE_PQ1), provider)

    def test_same_profile_id_with_weaker_aead_is_rejected(self) -> None:
        mutated = CryptoProfileV1(
            profile_id=OBJECT_SPACE_PQ1.profile_id,
            at_rest_aead="WEAK-AEAD",
            key_establishment=OBJECT_SPACE_PQ1.key_establishment,
            primary_signature=OBJECT_SPACE_PQ1.primary_signature,
            backup_signature=OBJECT_SPACE_PQ1.backup_signature,
            digest=OBJECT_SPACE_PQ1.digest,
        )
        with self.assertRaisesRegex(CryptoAgilityError, "downgrade|mutation"):
            require_profile(Provider(), mutated)

    def test_same_profile_id_with_weaker_kem_is_rejected(self) -> None:
        mutated = CryptoProfileV1(
            profile_id=OBJECT_SPACE_PQ1.profile_id,
            at_rest_aead=OBJECT_SPACE_PQ1.at_rest_aead,
            key_establishment="WEAK-KEM",
            primary_signature=OBJECT_SPACE_PQ1.primary_signature,
            backup_signature=OBJECT_SPACE_PQ1.backup_signature,
            digest=OBJECT_SPACE_PQ1.digest,
        )
        with self.assertRaisesRegex(CryptoAgilityError, "downgrade|mutation"):
            require_profile(Provider(), mutated)

    def test_unregistered_profile_id_is_rejected(self) -> None:
        mutated = CryptoProfileV1(
            profile_id="koschei-pq999",
            at_rest_aead=OBJECT_SPACE_PQ1.at_rest_aead,
            key_establishment=OBJECT_SPACE_PQ1.key_establishment,
            primary_signature=OBJECT_SPACE_PQ1.primary_signature,
            backup_signature=OBJECT_SPACE_PQ1.backup_signature,
            digest=OBJECT_SPACE_PQ1.digest,
        )
        with self.assertRaisesRegex(CryptoAgilityError, "unregistered"):
            require_profile(Provider(), mutated)


if __name__ == "__main__":
    unittest.main()
