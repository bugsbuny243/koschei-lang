"""Secure authority admission for canonical Koschei Object Space execution.

This boundary is intentionally explicit: provider capability, temporal secret,
short-lived handle, project identity and epoch are supplied by a trusted session
broker/host. Project bytes, filenames, environment variables and parser success
are never authority-selection inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .canonical_native_entrypoints_v1 import (
    CanonicalNativeCheckAuthorityV1,
    CanonicalNativeRunAuthorityV1,
    check_canonical_native_v1,
    run_canonical_native_v1,
)
from .crypto_agility_v1 import OBJECT_SPACE_PQ1, CryptoProfileV1, ObjectSpaceCryptoProvider, require_profile
from .object_space_v1 import ObjectSpaceProject, load_object_space_project
from .temporal_access_v1 import TemporalAccessPolicy


class CanonicalAuthorityAdmissionError(ValueError):
    """Raised when trusted authority material cannot admit canonical Object Space."""


@dataclass(frozen=True, slots=True)
class CanonicalAuthoritySessionV1:
    """Process-local authority bundle; secrets are deliberately absent from repr."""

    provider: ObjectSpaceCryptoProvider = field(repr=False)
    temporal_key: bytes = field(repr=False)
    temporal_handle: bytes = field(repr=False)
    expected_project_id: bytes = field(repr=False)
    expected_epoch: int
    profile: CryptoProfileV1 = field(default=OBJECT_SPACE_PQ1, repr=False)
    temporal_policy: TemporalAccessPolicy = field(default_factory=TemporalAccessPolicy, repr=False)

    def __post_init__(self) -> None:
        try:
            require_profile(self.provider, self.profile)
            if not isinstance(self.temporal_key, bytes) or len(self.temporal_key) != 64 or not any(self.temporal_key):
                raise ValueError
            if not isinstance(self.temporal_handle, bytes) or len(self.temporal_handle) != 64:
                raise ValueError
            if not isinstance(self.expected_project_id, bytes) or len(self.expected_project_id) != 16 or not any(self.expected_project_id):
                raise ValueError
            if not isinstance(self.expected_epoch, int) or isinstance(self.expected_epoch, bool) or not 1 <= self.expected_epoch <= (1 << 64) - 1:
                raise ValueError
        except Exception:
            raise CanonicalAuthorityAdmissionError("invalid canonical authority session") from None

    def __repr__(self) -> str:
        return (
            "CanonicalAuthoritySessionV1("
            f"provider_profile={self.profile.profile_id!r}, expected_epoch={self.expected_epoch}, secrets=<redacted>)"
        )


def admit_canonical_object_space_v1(
    path: str | Path,
    *,
    authority: CanonicalAuthoritySessionV1,
    now: float | int | None = None,
) -> ObjectSpaceProject:
    """Authenticate one Object Space project without fallback or authority guessing."""

    if not isinstance(authority, CanonicalAuthoritySessionV1):
        raise CanonicalAuthorityAdmissionError("canonical authority session is required")
    try:
        return load_object_space_project(
            path,
            provider=authority.provider,
            temporal_key=authority.temporal_key,
            temporal_handle=authority.temporal_handle,
            expected_project_id=authority.expected_project_id,
            expected_epoch=authority.expected_epoch,
            profile=authority.profile,
            temporal_policy=authority.temporal_policy,
            now=now,
        )
    except Exception:
        # Deliberately suppress provider/crypto/session exception detail at this
        # public boundary so secrets and provider internals cannot enter logs.
        raise CanonicalAuthorityAdmissionError("canonical Object Space authority admission failed") from None


def check_with_canonical_authority_v1(
    path: str | Path,
    *,
    authority: CanonicalAuthoritySessionV1,
    now: float | int | None = None,
) -> CanonicalNativeCheckAuthorityV1:
    project = admit_canonical_object_space_v1(path, authority=authority, now=now)
    return check_canonical_native_v1(project)


def run_with_canonical_authority_v1(
    path: str | Path,
    *,
    authority: CanonicalAuthoritySessionV1,
    now: float | int | None = None,
) -> CanonicalNativeRunAuthorityV1:
    project = admit_canonical_object_space_v1(path, authority=authority, now=now)
    return run_canonical_native_v1(project)
