"""Authenticated native confinement attestations for Koschei Lang v1.

This module does not implement an OS sandbox and does not treat policy metadata as
physical isolation. It authenticates a confinement observation emitted by a
trusted native runtime attester and binds that observation to the exact Lang
runtime/native execution basis that Fabric projects.

The verifier key is the trust root. A valid attestation proves only that the
configured attester authenticated the stated observation; kernel/container/VM
enforcement must be established by that attester outside this Python module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_CTX = b"koschei.native-confinement-attestation/v1\x00"
_OBSERVED_STATES = frozenset({"VERIFIED", "PARTIAL", "FAILED"})


class NativeConfinementAttestationV1Error(ValueError):
    """Raised when native confinement evidence is malformed or unauthenticated."""


def _require_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise NativeConfinementAttestationV1Error(
            "confinement verifier key must contain at least 32 bytes"
        )
    return value


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeConfinementAttestationV1Error(f"{field} is required")
    return value


def _require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise NativeConfinementAttestationV1Error(
            f"{field} must be lowercase SHA-256 hex"
        )
    return value


def _canonical_mechanisms(mechanisms: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(mechanisms, tuple) or not mechanisms:
        raise NativeConfinementAttestationV1Error(
            "confinement mechanisms must contain at least one entry"
        )
    if any(not isinstance(item, str) or not item.strip() for item in mechanisms):
        raise NativeConfinementAttestationV1Error(
            "confinement mechanisms must be non-empty strings"
        )
    if len(set(mechanisms)) != len(mechanisms):
        raise NativeConfinementAttestationV1Error(
            "confinement mechanisms must be unique"
        )
    return tuple(sorted(mechanisms))


def _payload(
    *,
    attester_id: str,
    observed_state: str,
    policy_version: str,
    runtime_version: str,
    revocation_epoch: int,
    native_digest_sha256: str,
    grant_digest_sha256: str | None,
    mechanisms: tuple[str, ...],
) -> bytes:
    rows = (
        f"attester={attester_id}",
        f"state={observed_state}",
        f"policy={policy_version}",
        f"runtime={runtime_version}",
        f"revocation_epoch={revocation_epoch}",
        f"native={native_digest_sha256}",
        f"grant={grant_digest_sha256 or '-'}",
        f"mechanisms={','.join(mechanisms)}",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class NativeConfinementAttestationV1:
    """Authenticated statement from a trusted native confinement observer."""

    attester_id: str
    observed_state: str
    policy_version: str
    runtime_version: str
    revocation_epoch: int
    native_digest_sha256: str
    grant_digest_sha256: str | None
    mechanisms: tuple[str, ...]
    attestation_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(
        self,
        *,
        verifier_key: bytes,
        trusted_attester_id: str,
        expected_policy_version: str,
        expected_runtime_version: str,
        expected_revocation_epoch: int,
        expected_native_digest_sha256: str,
        expected_grant_digest_sha256: str | None,
    ) -> None:
        """Verify authenticity and exact binding to one projection basis."""

        key = _require_key(verifier_key)
        trusted_attester_id = _require_text(
            trusted_attester_id, "trusted_attester_id"
        )
        if self.authority:
            raise NativeConfinementAttestationV1Error(
                "confinement attestation cannot carry ambient authority"
            )
        if self.version != 1:
            raise NativeConfinementAttestationV1Error(
                "unsupported confinement attestation version"
            )
        if self.attester_id != trusted_attester_id:
            raise NativeConfinementAttestationV1Error(
                "confinement attester is not trusted"
            )
        if self.observed_state not in _OBSERVED_STATES:
            raise NativeConfinementAttestationV1Error(
                "unsupported confinement observation state"
            )
        if (
            not isinstance(self.revocation_epoch, int)
            or isinstance(self.revocation_epoch, bool)
            or self.revocation_epoch < 0
        ):
            raise NativeConfinementAttestationV1Error(
                "revocation_epoch must be a non-negative integer"
            )

        _require_text(self.attester_id, "attester_id")
        _require_text(self.policy_version, "policy_version")
        _require_text(self.runtime_version, "runtime_version")
        native_digest = _require_sha256(
            self.native_digest_sha256, "native_digest_sha256"
        )
        expected_native_digest = _require_sha256(
            expected_native_digest_sha256, "expected_native_digest_sha256"
        )

        grant_digest = self.grant_digest_sha256
        if grant_digest is not None:
            grant_digest = _require_sha256(grant_digest, "grant_digest_sha256")
        expected_grant_digest = expected_grant_digest_sha256
        if expected_grant_digest is not None:
            expected_grant_digest = _require_sha256(
                expected_grant_digest, "expected_grant_digest_sha256"
            )

        mechanisms = _canonical_mechanisms(self.mechanisms)
        expected_fields = (
            (self.policy_version, expected_policy_version, "policy version"),
            (self.runtime_version, expected_runtime_version, "runtime version"),
            (self.revocation_epoch, expected_revocation_epoch, "revocation epoch"),
            (native_digest, expected_native_digest, "native digest"),
            (grant_digest, expected_grant_digest, "grant digest"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise NativeConfinementAttestationV1Error(
                    f"confinement attestation {label} mismatch"
                )

        if not isinstance(self.attestation_digest, str) or not _SHA256_RE.fullmatch(
            self.attestation_digest
        ):
            raise NativeConfinementAttestationV1Error(
                "attestation_digest must be lowercase SHA-256 hex"
            )
        expected = hmac.new(
            key,
            _payload(
                attester_id=self.attester_id,
                observed_state=self.observed_state,
                policy_version=self.policy_version,
                runtime_version=self.runtime_version,
                revocation_epoch=self.revocation_epoch,
                native_digest_sha256=native_digest,
                grant_digest_sha256=grant_digest,
                mechanisms=mechanisms,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(self.attestation_digest, expected):
            raise NativeConfinementAttestationV1Error(
                "confinement attestation authentication failed"
            )


def create_native_confinement_attestation_v1(
    *,
    attester_key: bytes,
    attester_id: str,
    observed_state: str,
    policy_version: str,
    runtime_version: str,
    revocation_epoch: int,
    native_digest_sha256: str,
    mechanisms: tuple[str, ...],
    grant_digest_sha256: str | None = None,
) -> NativeConfinementAttestationV1:
    """Create an authenticated observation for tests/native attester adapters.

    Possession of ``attester_key`` is the trust boundary. Callers must not treat
    this helper as evidence that an OS sandbox exists; production keys belong in
    the native confinement attester that actually observes/enforces isolation.
    """

    key = _require_key(attester_key)
    attester_id = _require_text(attester_id, "attester_id")
    policy_version = _require_text(policy_version, "policy_version")
    runtime_version = _require_text(runtime_version, "runtime_version")
    if observed_state not in _OBSERVED_STATES:
        raise NativeConfinementAttestationV1Error(
            "unsupported confinement observation state"
        )
    if (
        not isinstance(revocation_epoch, int)
        or isinstance(revocation_epoch, bool)
        or revocation_epoch < 0
    ):
        raise NativeConfinementAttestationV1Error(
            "revocation_epoch must be a non-negative integer"
        )
    native_digest = _require_sha256(native_digest_sha256, "native_digest_sha256")
    grant_digest = grant_digest_sha256
    if grant_digest is not None:
        grant_digest = _require_sha256(grant_digest, "grant_digest_sha256")
    canonical_mechanisms = _canonical_mechanisms(mechanisms)

    digest = hmac.new(
        key,
        _payload(
            attester_id=attester_id,
            observed_state=observed_state,
            policy_version=policy_version,
            runtime_version=runtime_version,
            revocation_epoch=revocation_epoch,
            native_digest_sha256=native_digest,
            grant_digest_sha256=grant_digest,
            mechanisms=canonical_mechanisms,
        ),
        hashlib.sha256,
    ).hexdigest()
    return NativeConfinementAttestationV1(
        attester_id=attester_id,
        observed_state=observed_state,
        policy_version=policy_version,
        runtime_version=runtime_version,
        revocation_epoch=revocation_epoch,
        native_digest_sha256=native_digest,
        grant_digest_sha256=grant_digest,
        mechanisms=canonical_mechanisms,
        attestation_digest=digest,
    )


def assert_verified_native_confinement_v1(
    attestation: NativeConfinementAttestationV1,
    *,
    verifier_key: bytes,
    trusted_attester_id: str,
    expected_policy_version: str,
    expected_runtime_version: str,
    expected_revocation_epoch: int,
    expected_native_digest_sha256: str,
    expected_grant_digest_sha256: str | None,
) -> None:
    """Require an authenticated VERIFIED observation bound to exact runtime state."""

    if not isinstance(attestation, NativeConfinementAttestationV1):
        raise NativeConfinementAttestationV1Error(
            "native confinement attestation is required"
        )
    attestation.assert_authenticated(
        verifier_key=verifier_key,
        trusted_attester_id=trusted_attester_id,
        expected_policy_version=expected_policy_version,
        expected_runtime_version=expected_runtime_version,
        expected_revocation_epoch=expected_revocation_epoch,
        expected_native_digest_sha256=expected_native_digest_sha256,
        expected_grant_digest_sha256=expected_grant_digest_sha256,
    )
    if attestation.observed_state != "VERIFIED":
        raise NativeConfinementAttestationV1Error(
            "native confinement observation is not VERIFIED"
        )
