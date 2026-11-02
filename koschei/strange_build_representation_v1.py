"""Trust-Plane-scoped, deterministic identifiers for Strange native projections.

Only the *representation* is varied. Canonical MIR identities and authority
remain unchanged. The deployment seed must be supplied by a trusted builder;
there is intentionally no public CLI argument, ambient environment lookup,
or serialized seed/identity mapping in this module.
"""
from __future__ import annotations

import base64
import hashlib
import hmac


_DOMAIN = b"koschei/strange-native-symbol/v1\x00"


class StrangeBuildRepresentationError(ValueError):
    """The requested representation cannot be safely derived."""


def derive_strange_symbol(*, seed: bytes, role: str, identity: str) -> str:
    """Produce a stable Go-safe opaque symbol for one scoped symbol identity.

    Different seeds produce distinct representations for the same canonical
    program. This is name diversification, NOT source encryption, a signature,
    or an execution-authority grant.
    """
    if not isinstance(seed, bytes) or len(seed) < 32:
        raise StrangeBuildRepresentationError("trusted deployment seed must be at least 256 bits")
    if role not in ("function", "parameter"):
        raise StrangeBuildRepresentationError("unsupported representation role")
    if not isinstance(identity, str) or not identity:
        raise StrangeBuildRepresentationError("canonical symbol identity is required")
    identity_bytes = identity.encode("utf-8")
    message = (
        _DOMAIN
        + len(role).to_bytes(2, "big")
        + role.encode("ascii")
        + len(identity_bytes).to_bytes(8, "big")
        + identity_bytes
    )
    digest = hmac.new(seed, message, hashlib.sha256).digest()[:20]
    return "_k_" + base64.b32encode(digest).decode("ascii").rstrip("=").lower()
