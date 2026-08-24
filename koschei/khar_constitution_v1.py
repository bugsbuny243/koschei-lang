"""Canonical Koschei Khar constitution v1.

Khar laws are intentionally public.  Security must not depend on hiding them.
What is forbidden is substitution: a caller may not invent a different law set
and still pass the strongest Koschei Galaxy gate as Khar v1.

This first version is deliberately rigid.  The canonical law set and its digest
are derived in code; Veyra identity may bind to that digest, and constitutional
execution requires the exact canonical digest.  Future extensions must use an
explicit successor-constitution protocol rather than silently rewriting v1.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .galaxy_identity_v1 import VeyraIdentity, birth_veyra

_CTX = b"koschei.khar-constitution/v1\x00"


class KharConstitutionError(ValueError):
    pass


# These are the constitutional laws already represented in the strongest
# current Galaxy execution path.  They are public identifiers, not secrets.
CANONICAL_KHAR_LAWS_V1 = (
    "khar.non-weakening",
    "khar.sathra.exact-six",
    "khar.sathra.axis-non-substitution",
    "khar.sathra.exact-event",
    "khar.sathra.one-shot-finality",
    "khar.axis.failure-root-separation",
    "khar.aevra.no-resurrection",
    "khar.matrix.current-hara-only",
    "khar.survival.plan-is-not-authority",
)


def _constitution_digest(laws: tuple[str, ...]) -> str:
    if not laws or any(not isinstance(law, str) or not law for law in laws):
        raise KharConstitutionError("Khar laws must be non-empty public identifiers")
    if len(set(laws)) != len(laws):
        raise KharConstitutionError("duplicate Khar law identifier")
    payload = "\n".join(laws).encode("utf-8")
    return hashlib.sha256(_CTX + b"laws\x00" + payload).hexdigest()


CANONICAL_KHAR_DIGEST_V1 = _constitution_digest(CANONICAL_KHAR_LAWS_V1)


@dataclass(frozen=True, slots=True)
class KharConstitutionV1:
    laws: tuple[str, ...]
    digest: str
    version: int = 1

    def assert_canonical(self) -> None:
        if self.version != 1:
            raise KharConstitutionError("unsupported Khar constitution version")
        if self.laws != CANONICAL_KHAR_LAWS_V1:
            raise KharConstitutionError("Khar v1 law substitution is forbidden")
        expected = _constitution_digest(self.laws)
        if expected != CANONICAL_KHAR_DIGEST_V1 or self.digest != expected:
            raise KharConstitutionError("Khar v1 constitution seal mismatch")


def canonical_khar_v1() -> KharConstitutionV1:
    result = KharConstitutionV1(CANONICAL_KHAR_LAWS_V1, CANONICAL_KHAR_DIGEST_V1)
    result.assert_canonical()
    return result


def birth_canonical_veyra(
    *,
    profile_digest: str,
    genesis_digest: str,
    instance_digest: str,
    birth_epoch: int,
) -> VeyraIdentity:
    """Birth a Veyra bound to the exact canonical Khar v1 law digest."""

    return birth_veyra(
        profile_digest=profile_digest,
        genesis_digest=genesis_digest,
        constitution_digest=CANONICAL_KHAR_DIGEST_V1,
        instance_digest=instance_digest,
        birth_epoch=birth_epoch,
    )


def require_canonical_khar_v1(veyra: VeyraIdentity) -> KharConstitutionV1:
    """Reject any Veyra whose constitutional identity is caller-substituted."""

    try:
        veyra.assert_sealed()
    except ValueError as error:
        raise KharConstitutionError(str(error)) from error
    constitution = canonical_khar_v1()
    if veyra.constitution_digest != constitution.digest:
        raise KharConstitutionError(
            "Veyra is not bound to the canonical Khar v1 constitution"
        )
    return constitution
