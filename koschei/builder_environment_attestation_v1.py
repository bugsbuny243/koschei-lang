"""Builder environment attestation for Koschei Lang v1.

Binds a logical builder identity to one authenticated execution-environment identity,
workload measurement and epoch. This is provenance, not authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

_CTX = b"koschei.builder-environment-attestation/v1\x00"
_ENV_CTX = b"koschei.builder-environment-measurement/v1\x00"
_WORKLOAD_CTX = b"koschei.builder-workload-measurement/v1\x00"


class BuilderEnvironmentAttestationV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise BuilderEnvironmentAttestationV1Error("environment_attestation_key must contain at least 32 bytes")
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuilderEnvironmentAttestationV1Error(f"{label} cannot be empty")
    return value.strip()


def _epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BuilderEnvironmentAttestationV1Error("epoch must be a non-negative integer")
    return value


def measure_builder_environment_v1(environment_bytes: bytes) -> str:
    if not isinstance(environment_bytes, bytes) or not environment_bytes:
        raise BuilderEnvironmentAttestationV1Error("environment_bytes must be non-empty bytes")
    return hashlib.sha256(_ENV_CTX + environment_bytes).hexdigest()


def measure_builder_workload_v1(workload_bytes: bytes) -> str:
    if not isinstance(workload_bytes, bytes) or not workload_bytes:
        raise BuilderEnvironmentAttestationV1Error("workload_bytes must be non-empty bytes")
    return hashlib.sha256(_WORKLOAD_CTX + workload_bytes).hexdigest()


def _payload(*, builder_id: str, environment_id: str, environment_digest: str,
             workload_digest: str, attestation_authority_id: str, epoch: int) -> bytes:
    rows = (
        f"builder={builder_id}", f"environment_id={environment_id}",
        f"environment={environment_digest}", f"workload={workload_digest}",
        f"authority_id={attestation_authority_id}", f"epoch={epoch}", "authority=0",
    )
    return _CTX + "\n".join(rows).encode()


@dataclass(frozen=True, slots=True)
class BuilderEnvironmentAttestationV1:
    builder_id: str
    environment_id: str
    environment_digest: str
    workload_digest: str
    attestation_authority_id: str
    epoch: int
    attestation_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, environment_attestation_key: bytes,
                             environment_bytes: bytes, workload_bytes: bytes) -> None:
        key = _key(environment_attestation_key)
        if self.authority:
            raise BuilderEnvironmentAttestationV1Error("builder environment attestation cannot carry ambient authority")
        if self.environment_digest != measure_builder_environment_v1(environment_bytes):
            raise BuilderEnvironmentAttestationV1Error("builder environment measurement mismatch")
        if self.workload_digest != measure_builder_workload_v1(workload_bytes):
            raise BuilderEnvironmentAttestationV1Error("builder workload measurement mismatch")
        expected = hmac.new(key, _payload(
            builder_id=_text(self.builder_id, "builder_id"),
            environment_id=_text(self.environment_id, "environment_id"),
            environment_digest=self.environment_digest,
            workload_digest=self.workload_digest,
            attestation_authority_id=_text(self.attestation_authority_id, "attestation_authority_id"),
            epoch=_epoch(self.epoch),
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.attestation_digest, expected):
            raise BuilderEnvironmentAttestationV1Error("builder environment attestation authentication failed")


def attest_builder_environment_v1(*, builder_id: str, environment_id: str,
                                  environment_bytes: bytes, workload_bytes: bytes,
                                  attestation_authority_id: str, epoch: int,
                                  environment_attestation_key: bytes) -> BuilderEnvironmentAttestationV1:
    key = _key(environment_attestation_key)
    result = BuilderEnvironmentAttestationV1(
        builder_id=_text(builder_id, "builder_id"),
        environment_id=_text(environment_id, "environment_id"),
        environment_digest=measure_builder_environment_v1(environment_bytes),
        workload_digest=measure_builder_workload_v1(workload_bytes),
        attestation_authority_id=_text(attestation_authority_id, "attestation_authority_id"),
        epoch=_epoch(epoch), attestation_digest="",
    )
    object.__setattr__(result, "attestation_digest", hmac.new(key, _payload(
        builder_id=result.builder_id, environment_id=result.environment_id,
        environment_digest=result.environment_digest, workload_digest=result.workload_digest,
        attestation_authority_id=result.attestation_authority_id, epoch=result.epoch,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(environment_attestation_key=key, environment_bytes=environment_bytes, workload_bytes=workload_bytes)
    return result
