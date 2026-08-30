"""Authenticated compiler/toolchain provenance for Koschei Lang v1.

This module binds one exact toolchain artifact byte string to a deterministic
non-authoritative identity. It does not prove compiler correctness; it proves which
artifact/version/profile metadata was authenticated under a protected toolchain key.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

_CTX = b"koschei.toolchain-provenance/v1\x00"
_ARTIFACT_CTX = b"koschei.toolchain-artifact/v1\x00"


class ToolchainProvenanceV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ToolchainProvenanceV1Error("toolchain_signing_key must contain at least 32 bytes")
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolchainProvenanceV1Error(f"{label} cannot be empty")
    return value.strip()


def measure_toolchain_artifact_v1(artifact_bytes: bytes) -> str:
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise ToolchainProvenanceV1Error("toolchain artifact bytes must be non-empty")
    return hashlib.sha256(_ARTIFACT_CTX + artifact_bytes).hexdigest()


def _payload(*, toolchain_id: str, toolchain_version: str,
             artifact_digest: str, build_profile: str) -> bytes:
    rows = (
        f"toolchain={toolchain_id}",
        f"version={toolchain_version}",
        f"artifact={artifact_digest}",
        f"profile={build_profile}",
        "authority=0",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ToolchainProvenanceV1:
    toolchain_id: str
    toolchain_version: str
    artifact_digest: str
    build_profile: str
    provenance_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, toolchain_signing_key: bytes,
                             toolchain_artifact_bytes: bytes) -> None:
        key = _key(toolchain_signing_key)
        if self.authority:
            raise ToolchainProvenanceV1Error("toolchain provenance cannot carry ambient authority")
        measured = measure_toolchain_artifact_v1(toolchain_artifact_bytes)
        if self.artifact_digest != measured:
            raise ToolchainProvenanceV1Error("toolchain artifact mismatch")
        expected = hmac.new(key, _payload(
            toolchain_id=_text(self.toolchain_id, "toolchain_id"),
            toolchain_version=_text(self.toolchain_version, "toolchain_version"),
            artifact_digest=self.artifact_digest,
            build_profile=_text(self.build_profile, "build_profile"),
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.provenance_digest, expected):
            raise ToolchainProvenanceV1Error("toolchain provenance authentication failed")


def attest_toolchain_provenance_v1(*, toolchain_id: str,
                                   toolchain_version: str,
                                   toolchain_artifact_bytes: bytes,
                                   build_profile: str,
                                   toolchain_signing_key: bytes) -> ToolchainProvenanceV1:
    key = _key(toolchain_signing_key)
    result = ToolchainProvenanceV1(
        toolchain_id=_text(toolchain_id, "toolchain_id"),
        toolchain_version=_text(toolchain_version, "toolchain_version"),
        artifact_digest=measure_toolchain_artifact_v1(toolchain_artifact_bytes),
        build_profile=_text(build_profile, "build_profile"),
        provenance_digest="",
    )
    object.__setattr__(result, "provenance_digest", hmac.new(key, _payload(
        toolchain_id=result.toolchain_id,
        toolchain_version=result.toolchain_version,
        artifact_digest=result.artifact_digest,
        build_profile=result.build_profile,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(
        toolchain_signing_key=key,
        toolchain_artifact_bytes=toolchain_artifact_bytes,
    )
    return result
