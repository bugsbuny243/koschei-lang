"""Koschei Fabric case-envelope projection for Koschei Lang.

This adapter never derives authority from Fabric JSON, Sentinel output, tool
metadata, or arbitrary external input. It only projects an already-evaluated
Lang-native authority/runtime result into the shared Fabric envelope shape.

A Fabric ``isolationState=VERIFIED`` claim is proof-gated: metadata alone cannot
create it. The caller must provide an authenticated native confinement
attestation bound to the exact policy/runtime/revocation/native/grant basis.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .native_confinement_attestation_v1 import (
    NativeConfinementAttestationV1,
    assert_verified_native_confinement_v1,
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_AUTHORITY_STATES = frozenset({"AUTHORIZED", "DENIED", "REVOKED", "UNVERIFIED", "UNKNOWN"})
_ISOLATION_STATES = frozenset({"VERIFIED", "PARTIAL", "UNVERIFIED", "UNAVAILABLE"})


@dataclass(frozen=True, slots=True)
class FabricLangProjectionV1:
    authority: dict[str, object]
    runtime: dict[str, object]
    native_binding: dict[str, object]


def _require_sha256(value: str, field: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256 hex")
    return value


def build_lang_fabric_projection_v1(
    *,
    principal: str,
    caller: str,
    scope: tuple[str, ...],
    authority_state: str,
    policy_version: str,
    runtime_version: str,
    revocation_epoch: int,
    isolation_state: str,
    max_calls: int,
    max_duration_ms: int,
    max_data_bytes: int,
    native_schema: str,
    native_ref: str,
    native_digest_sha256: str,
    adapter_version: str = "lang.fabric-case-adapter.v1",
    delegate: str | None = None,
    not_before: str | None = None,
    expires_at: str | None = None,
    grant_digest_sha256: str | None = None,
    max_spend_minor_units: int | None = None,
    mapping_state: str = "PARTIAL",
    confinement_attestation: NativeConfinementAttestationV1 | None = None,
    confinement_verifier_key: bytes | None = None,
    trusted_confinement_attester_id: str | None = None,
) -> FabricLangProjectionV1:
    """Project a Lang-native decision without widening its scope or authority.

    ``VERIFIED`` isolation is fail-closed. It requires an authenticated native
    attestation bound to this exact projection. Weaker isolation states remain
    backward compatible and do not require confinement evidence.
    """
    if not principal.strip() or not caller.strip():
        raise ValueError("principal and caller are required")
    if not scope or any(not item.strip() for item in scope):
        raise ValueError("scope must contain at least one non-empty entry")
    if len(set(scope)) != len(scope):
        raise ValueError("scope entries must be unique")
    if authority_state not in _AUTHORITY_STATES:
        raise ValueError("unsupported authority state")
    if isolation_state not in _ISOLATION_STATES:
        raise ValueError("unsupported isolation state")
    if mapping_state not in {"VERIFIED", "PARTIAL", "UNVERIFIED"}:
        raise ValueError("unsupported mapping state")
    for name, value in {
        "revocation_epoch": revocation_epoch,
        "max_calls": max_calls,
        "max_duration_ms": max_duration_ms,
        "max_data_bytes": max_data_bytes,
    }.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if max_spend_minor_units is not None and max_spend_minor_units < 0:
        raise ValueError("max_spend_minor_units must be non-negative")
    if not policy_version.strip() or not runtime_version.strip():
        raise ValueError("policy_version and runtime_version are required")
    if not native_schema.strip() or not native_ref.strip() or not adapter_version.strip():
        raise ValueError("native schema/ref and adapter version are required")

    native_digest = _require_sha256(native_digest_sha256, "native_digest_sha256")
    grant_digest = None
    if grant_digest_sha256 is not None:
        grant_digest = _require_sha256(grant_digest_sha256, "grant_digest_sha256")

    if isolation_state == "VERIFIED":
        if confinement_attestation is None:
            raise ValueError(
                "VERIFIED isolation requires an authenticated native confinement attestation"
            )
        if confinement_verifier_key is None:
            raise ValueError("VERIFIED isolation requires a confinement verifier key")
        if trusted_confinement_attester_id is None:
            raise ValueError("VERIFIED isolation requires a trusted confinement attester id")
        assert_verified_native_confinement_v1(
            confinement_attestation,
            verifier_key=confinement_verifier_key,
            trusted_attester_id=trusted_confinement_attester_id,
            expected_policy_version=policy_version,
            expected_runtime_version=runtime_version,
            expected_revocation_epoch=revocation_epoch,
            expected_native_digest_sha256=native_digest,
            expected_grant_digest_sha256=grant_digest,
        )

    authority: dict[str, object] = {
        "authorityOwner": "koschei-lang",
        "principal": principal,
        "caller": caller,
        "delegate": delegate,
        "scope": list(scope),
        "notBefore": not_before,
        "expiresAt": expires_at,
        "authorityState": authority_state,
        "grantDigestSha256": grant_digest,
    }
    runtime: dict[str, object] = {
        "runtimeOwner": "koschei-lang",
        "policyVersion": policy_version,
        "runtimeVersion": runtime_version,
        "revocationEpoch": revocation_epoch,
        "isolationState": isolation_state,
        "budget": {
            "maxCalls": max_calls,
            "maxDurationMs": max_duration_ms,
            "maxDataBytes": max_data_bytes,
            "maxSpendMinorUnits": max_spend_minor_units,
        },
    }
    native_binding: dict[str, object] = {
        "owner": "koschei-lang",
        "nativeSchema": native_schema,
        "nativeRef": native_ref,
        "nativeDigestSha256": native_digest,
        "adapterVersion": adapter_version,
        "mappingState": mapping_state,
    }
    return FabricLangProjectionV1(authority=authority, runtime=runtime, native_binding=native_binding)


def fabric_lang_projection_payload_v1(**kwargs: object) -> dict[str, object]:
    """Return the adapter projection as plain JSON-serializable data."""
    return asdict(build_lang_fabric_projection_v1(**kwargs))
