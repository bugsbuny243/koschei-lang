"""Crypto-agility contract for Koschei Object Space v1.

Koschei does not implement new cryptographic primitives for originality. The
language/project model may be original; the cryptography must remain replaceable
and delegated to audited providers that implement standardized algorithms.

Object Space v1 deliberately ships *no* default AEAD/PQC implementation. A
provider must be supplied by the trusted runtime/session layer. This keeps the
compiler's zero-third-party-dependency rule while preventing a home-grown crypto
fallback from becoming canonical by accident.

Profile identifiers are registry identities, not cosmetic labels. A caller cannot
reuse a registered id while silently changing its algorithm contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
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


# High-assurance starting profile. Algorithm names are identifiers for an
# external audited provider; this module does not implement these algorithms.
OBJECT_SPACE_PQ1 = CryptoProfileV1(
    profile_id="koschei-pq1",
    at_rest_aead="AES-256-GCM",
    key_establishment="ML-KEM-1024",
    primary_signature="ML-DSA-87",
    backup_signature="SLH-DSA",
    digest="SHA3-512",
)

_PROFILE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_REGISTERED_PROFILES_V1 = {
    OBJECT_SPACE_PQ1.profile_id: OBJECT_SPACE_PQ1,
}


@runtime_checkable
class ObjectSpaceCryptoProvider(Protocol):
    """External audited cryptographic provider bound to one profile.

    The provider owns key custody. No secret key is accepted as a raw argument
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


def _validate_profile_shape(profile: object) -> CryptoProfileV1:
    if not isinstance(profile, CryptoProfileV1):
        raise CryptoAgilityError("crypto profile must use the canonical CryptoProfileV1 record")
    fields = (
        profile.profile_id,
        profile.at_rest_aead,
        profile.key_establishment,
        profile.primary_signature,
        profile.backup_signature,
        profile.digest,
    )
    if any(
        not isinstance(value, str)
        or _PROFILE_TOKEN_RE.fullmatch(value) is None
        for value in fields
    ):
        raise CryptoAgilityError(
            "crypto profile fields must be canonical non-empty ASCII identifiers"
        )
    return profile


def require_profile(
    provider: ObjectSpaceCryptoProvider,
    profile: CryptoProfileV1 = OBJECT_SPACE_PQ1,
) -> ObjectSpaceCryptoProvider:
    selected = _validate_profile_shape(profile)
    canonical = _REGISTERED_PROFILES_V1.get(selected.profile_id)
    if canonical is None:
        raise CryptoAgilityError(
            f"unregistered object-space crypto profile: {selected.profile_id!r}"
        )
    if selected != canonical:
        raise CryptoAgilityError(
            f"crypto profile downgrade/mutation rejected for registered id {selected.profile_id!r}"
        )
    if not isinstance(provider, ObjectSpaceCryptoProvider):
        raise CryptoAgilityError(
            "object-space crypto provider does not implement the canonical provider contract"
        )
    if provider.profile_id != canonical.profile_id:
        raise CryptoAgilityError(
            f"crypto profile mismatch: expected {canonical.profile_id!r}, "
            f"got {provider.profile_id!r}"
        )
    return provider
