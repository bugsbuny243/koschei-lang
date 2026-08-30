"""Builder environment attestation for Koschei Lang v1.

Binds a logical builder identity to one authenticated execution-environment identity,
workload measurement and epoch, backed by provider-neutral remote-attestation evidence.
Downstream validation requires the remote evidence to remain current under the supplied
trust-anchor generation state. This is provenance, not authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .remote_attestation_evidence_v1 import RemoteAttestationEvidenceV1
from .trust_anchor_admission_v1 import TrustAnchorGenerationStateV1

_CTX = b"koschei.builder-environment-attestation/v1\x00"
_ENV_CTX = b"koschei.builder-environment-measurement/v1\x00"
_WORKLOAD_CTX = b"koschei.builder-workload-measurement/v1\x00"

class BuilderEnvironmentAttestationV1Error(ValueError): pass

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

def _generation(value:int)->int:
    if not isinstance(value,int) or isinstance(value,bool) or value<0:
        raise BuilderEnvironmentAttestationV1Error("generation must be a non-negative integer")
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
             workload_digest: str, attestation_authority_id: str, epoch: int,
             remote_evidence_digest: str, trust_root_id: str, trust_anchor_id:str,
             trust_anchor_generation:int, trust_anchor_manifest_digest:str) -> bytes:
    rows = (
        f"builder={builder_id}", f"environment_id={environment_id}",
        f"environment={environment_digest}", f"workload={workload_digest}",
        f"authority_id={attestation_authority_id}", f"epoch={epoch}",
        f"remote_evidence={remote_evidence_digest}", f"trust_root={trust_root_id}",
        f"trust_anchor_id={trust_anchor_id}", f"trust_anchor_generation={trust_anchor_generation}",
        f"trust_anchor_manifest={trust_anchor_manifest_digest}", "authority=0",
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
    remote_attestation_evidence_digest: str
    trust_root_id: str
    trust_anchor_id: str
    trust_anchor_generation: int
    trust_anchor_manifest_digest: str
    attestation_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, environment_attestation_key: bytes,
                             environment_bytes: bytes, workload_bytes: bytes,
                             remote_evidence: RemoteAttestationEvidenceV1,
                             raw_remote_evidence_bytes: bytes,
                             remote_attestation_verifier_key: bytes,
                             current_epoch: int,
                             trust_anchor_generation_state:TrustAnchorGenerationStateV1) -> None:
        key = _key(environment_attestation_key)
        current = _epoch(current_epoch)
        remote_evidence.assert_authenticated(remote_attestation_verifier_key=remote_attestation_verifier_key,raw_evidence_bytes=raw_remote_evidence_bytes,current_epoch=current)
        remote_evidence.assert_current_generation(trust_anchor_generation_state=trust_anchor_generation_state)
        if self.authority:
            raise BuilderEnvironmentAttestationV1Error("builder environment attestation cannot carry ambient authority")
        if self.environment_digest != measure_builder_environment_v1(environment_bytes): raise BuilderEnvironmentAttestationV1Error("builder environment measurement mismatch")
        if self.workload_digest != measure_builder_workload_v1(workload_bytes): raise BuilderEnvironmentAttestationV1Error("builder workload measurement mismatch")
        if remote_evidence.environment_digest != self.environment_digest: raise BuilderEnvironmentAttestationV1Error("remote attestation environment measurement mismatch")
        if remote_evidence.workload_digest != self.workload_digest: raise BuilderEnvironmentAttestationV1Error("remote attestation workload measurement mismatch")
        if self.remote_attestation_evidence_digest != remote_evidence.evidence_digest: raise BuilderEnvironmentAttestationV1Error("builder environment remote evidence mismatch")
        if self.trust_root_id != remote_evidence.trust_root_id: raise BuilderEnvironmentAttestationV1Error("builder environment trust-root mismatch")
        if self.epoch != remote_evidence.observed_epoch: raise BuilderEnvironmentAttestationV1Error("builder environment epoch differs from remote evidence")
        if self.trust_anchor_id!=remote_evidence.trust_anchor_id or self.trust_anchor_generation!=remote_evidence.trust_anchor_generation or self.trust_anchor_manifest_digest!=remote_evidence.trust_anchor_manifest_digest:
            raise BuilderEnvironmentAttestationV1Error("builder environment trust-anchor generation binding mismatch")
        expected = hmac.new(key, _payload(
            builder_id=_text(self.builder_id, "builder_id"), environment_id=_text(self.environment_id, "environment_id"),
            environment_digest=self.environment_digest, workload_digest=self.workload_digest,
            attestation_authority_id=_text(self.attestation_authority_id, "attestation_authority_id"), epoch=_epoch(self.epoch),
            remote_evidence_digest=self.remote_attestation_evidence_digest, trust_root_id=_text(self.trust_root_id, "trust_root_id"),
            trust_anchor_id=_text(self.trust_anchor_id,"trust_anchor_id"), trust_anchor_generation=_generation(self.trust_anchor_generation),
            trust_anchor_manifest_digest=_text(self.trust_anchor_manifest_digest,"trust_anchor_manifest_digest"),
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.attestation_digest, expected): raise BuilderEnvironmentAttestationV1Error("builder environment attestation authentication failed")

def attest_builder_environment_v1(*, builder_id: str, environment_id: str,
                                  environment_bytes: bytes, workload_bytes: bytes,
                                  attestation_authority_id: str,
                                  environment_attestation_key: bytes,
                                  remote_evidence: RemoteAttestationEvidenceV1,
                                  raw_remote_evidence_bytes: bytes,
                                  remote_attestation_verifier_key: bytes,
                                  trust_anchor_generation_state:TrustAnchorGenerationStateV1) -> BuilderEnvironmentAttestationV1:
    key = _key(environment_attestation_key)
    remote_evidence.assert_authenticated(remote_attestation_verifier_key=remote_attestation_verifier_key,raw_evidence_bytes=raw_remote_evidence_bytes,current_epoch=remote_evidence.observed_epoch)
    remote_evidence.assert_current_generation(trust_anchor_generation_state=trust_anchor_generation_state)
    environment_digest = measure_builder_environment_v1(environment_bytes); workload_digest = measure_builder_workload_v1(workload_bytes)
    if remote_evidence.environment_digest != environment_digest: raise BuilderEnvironmentAttestationV1Error("remote attestation environment measurement mismatch")
    if remote_evidence.workload_digest != workload_digest: raise BuilderEnvironmentAttestationV1Error("remote attestation workload measurement mismatch")
    result = BuilderEnvironmentAttestationV1(
        builder_id=_text(builder_id, "builder_id"), environment_id=_text(environment_id, "environment_id"),
        environment_digest=environment_digest, workload_digest=workload_digest,
        attestation_authority_id=_text(attestation_authority_id, "attestation_authority_id"), epoch=remote_evidence.observed_epoch,
        remote_attestation_evidence_digest=remote_evidence.evidence_digest, trust_root_id=remote_evidence.trust_root_id,
        trust_anchor_id=remote_evidence.trust_anchor_id, trust_anchor_generation=remote_evidence.trust_anchor_generation,
        trust_anchor_manifest_digest=remote_evidence.trust_anchor_manifest_digest, attestation_digest="",
    )
    object.__setattr__(result, "attestation_digest", hmac.new(key, _payload(
        builder_id=result.builder_id, environment_id=result.environment_id, environment_digest=result.environment_digest,
        workload_digest=result.workload_digest, attestation_authority_id=result.attestation_authority_id, epoch=result.epoch,
        remote_evidence_digest=result.remote_attestation_evidence_digest, trust_root_id=result.trust_root_id,
        trust_anchor_id=result.trust_anchor_id, trust_anchor_generation=result.trust_anchor_generation,
        trust_anchor_manifest_digest=result.trust_anchor_manifest_digest,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(environment_attestation_key=key,environment_bytes=environment_bytes,workload_bytes=workload_bytes,
        remote_evidence=remote_evidence,raw_remote_evidence_bytes=raw_remote_evidence_bytes,
        remote_attestation_verifier_key=remote_attestation_verifier_key,current_epoch=remote_evidence.observed_epoch,
        trust_anchor_generation_state=trust_anchor_generation_state)
    return result
