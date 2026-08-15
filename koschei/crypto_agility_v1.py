"""Crypto-agility contract for Koschei Object Space v1.

Koschei does not implement new cryptographic primitives for originality.  The
language/project model may be original; the cryptography must remain replaceable
and delegated to audited providers that implement standardized algorithms.

Object Space v1 deliberately ships *no* default AEAD/PQC implementation.  A
provider must be supplied by the trusted runtime/session layer.  This keeps the
compiler's zero-third-party-dependency rule while preventing a home-grown crypto
fallback from becoming canonical by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class CryptoAgilityError(ValueError):
    """Raised when a crypto profile/provider contract is not satisfied."""


@dataclass(frozen=True, slots=True)
class CryptoProfileV1:
    profile_id: str
    at_rest_aead: str
    key_establishment: str
    primary_signature: str
    backup_signature: str
    digest: str


# High-assurance starting profile.  Algorithm names are identifiers for an
# external audited provider; this module does not implement these algorithms.
OBJECT_SPACE_PQ1 = CryptoProfileV1(
    profile_id="koschei-pq1",
    at_rest_aead="AES-256-GCM",
    key_establishment="ML-KEM-1024",
    primary_signature="ML-DSA-87",
    backup_signature="SLH-DSA",
    digest="SHA3-512",
)


@runtime_checkable
class ObjectSpaceCryptoProvider(Protocol):
    """External audited cryptographic provider bound to one profile.

    The provider owns key custody.  No secret key is accepted as a raw argument
    by Object Space storage APIs.
    """

    @property
    def profile_id(self) -> str: ...

    def seal(
        self,
        *,
        purpose: bytes,
        associated_data: bytes,
        plaintext: bytes,
    ) -> bytes: ...

    def open(
        self,
        *,
        purpose: bytes,
        associated_data: bytes,
        ciphertext: bytes,
    ) -> bytes: ...


def require_profile(
    provider: ObjectSpaceCryptoProvider,
    profile: CryptoProfileV1 = OBJECT_SPACE_PQ1,
) -> ObjectSpaceCryptoProvider:
    if not isinstance(provider, ObjectSpaceCryptoProvider):
        raise CryptoAgilityError(
            "object-space crypto provider does not implement the canonical provider contract"
        )
    if provider.profile_id != profile.profile_id:
        raise CryptoAgilityError(
            f"crypto profile mismatch: expected {profile.profile_id!r}, "
            f"got {provider.profile_id!r}"
        )
    return provider
