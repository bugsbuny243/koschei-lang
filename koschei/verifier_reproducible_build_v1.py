"""Independent verifier reproducible-build verification for Koschei Lang v1.

Two independently authenticated builder observations must bind the same
VerifiedIrBuildInputV1, authenticated toolchain provenance, distinct authenticated
builder environments, and exact verifier artifact before a reproducibility receipt can
be sealed. This is provenance, not authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .builder_environment_attestation_v1 import BuilderEnvironmentAttestationV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .toolchain_provenance_v1 import ToolchainProvenanceV1
from .verified_ir_build_input_v1 import VerifiedIrBuildInputV1

_OBS_CTX = b"koschei.verifier-builder-observation/v1\x00"
_REPRO_CTX = b"koschei.verifier-reproducible-build/v1\x00"
_ARTIFACT_CTX = b"koschei.verifier-artifact/v1\x00"

class VerifierReproducibleBuildV1Error(ValueError): pass

def _key(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32: raise VerifierReproducibleBuildV1Error(f"{label} must contain at least 32 bytes")
    return value

def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise VerifierReproducibleBuildV1Error(f"{label} cannot be empty")
    return value.strip()

def _measure(artifact_bytes: bytes) -> str:
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes: raise VerifierReproducibleBuildV1Error("artifact_bytes must be non-empty bytes")
    return hashlib.sha256(_ARTIFACT_CTX + artifact_bytes).hexdigest()

def _obs_payload(*, builder_id:str, verified_input_digest:str, toolchain_provenance_digest:str, environment_attestation_digest:str, build_profile:str, artifact_digest:str)->bytes:
    rows=(f"builder={builder_id}",f"verified_input={verified_input_digest}",f"toolchain={toolchain_provenance_digest}",f"environment={environment_attestation_digest}",f"profile={build_profile}",f"artifact={artifact_digest}","authority=0")
    return _OBS_CTX+"\n".join(rows).encode()

@dataclass(frozen=True, slots=True)
class VerifierBuilderObservationV1:
    builder_id:str; verified_input_digest:str; toolchain_provenance_digest:str; environment_attestation_digest:str; build_profile:str; artifact_digest:str; observation_digest:str; authority:bool=False; version:int=1
    def assert_authenticated(self, *, builder_key:bytes, verified_input:VerifiedIrBuildInputV1, mir:NativeSigilMir, proof:NativeSigilProofBundle, toolchain:ToolchainProvenanceV1, toolchain_artifact_bytes:bytes, toolchain_signing_key:bytes, environment:BuilderEnvironmentAttestationV1, environment_bytes:bytes, workload_bytes:bytes, environment_attestation_key:bytes, artifact_bytes:bytes)->None:
        key=_key(builder_key,"builder_key"); verified_input.assert_sealed(mir=mir,proof=proof)
        toolchain.assert_authenticated(toolchain_signing_key=toolchain_signing_key,toolchain_artifact_bytes=toolchain_artifact_bytes)
        environment.assert_authenticated(environment_attestation_key=environment_attestation_key,environment_bytes=environment_bytes,workload_bytes=workload_bytes)
        if self.authority: raise VerifierReproducibleBuildV1Error("builder observation cannot carry ambient authority")
        if self.builder_id!=environment.builder_id: raise VerifierReproducibleBuildV1Error("builder observation environment builder mismatch")
        if self.verified_input_digest!=verified_input.build_input_digest: raise VerifierReproducibleBuildV1Error("builder observation verified-input mismatch")
        if self.toolchain_provenance_digest!=toolchain.provenance_digest: raise VerifierReproducibleBuildV1Error("builder observation toolchain provenance mismatch")
        if self.environment_attestation_digest!=environment.attestation_digest: raise VerifierReproducibleBuildV1Error("builder observation environment attestation mismatch")
        measured=_measure(artifact_bytes)
        if self.artifact_digest!=measured: raise VerifierReproducibleBuildV1Error("builder observation artifact mismatch")
        expected=hmac.new(key,_obs_payload(builder_id=_text(self.builder_id,"builder_id"),verified_input_digest=self.verified_input_digest,toolchain_provenance_digest=self.toolchain_provenance_digest,environment_attestation_digest=self.environment_attestation_digest,build_profile=_text(self.build_profile,"build_profile"),artifact_digest=self.artifact_digest),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.observation_digest,expected): raise VerifierReproducibleBuildV1Error("builder observation authentication failed")

def attest_builder_observation_v1(*, builder_id:str,builder_key:bytes,verified_input:VerifiedIrBuildInputV1,mir:NativeSigilMir,proof:NativeSigilProofBundle,toolchain:ToolchainProvenanceV1,toolchain_artifact_bytes:bytes,toolchain_signing_key:bytes,environment:BuilderEnvironmentAttestationV1,environment_bytes:bytes,workload_bytes:bytes,environment_attestation_key:bytes,artifact_bytes:bytes,build_profile:str)->VerifierBuilderObservationV1:
    key=_key(builder_key,"builder_key"); verified_input.assert_sealed(mir=mir,proof=proof)
    toolchain.assert_authenticated(toolchain_signing_key=toolchain_signing_key,toolchain_artifact_bytes=toolchain_artifact_bytes)
    environment.assert_authenticated(environment_attestation_key=environment_attestation_key,environment_bytes=environment_bytes,workload_bytes=workload_bytes)
    if builder_id!=environment.builder_id: raise VerifierReproducibleBuildV1Error("builder observation environment builder mismatch")
    result=VerifierBuilderObservationV1(_text(builder_id,"builder_id"),verified_input.build_input_digest,toolchain.provenance_digest,environment.attestation_digest,_text(build_profile,"build_profile"),_measure(artifact_bytes),"")
    object.__setattr__(result,"observation_digest",hmac.new(key,_obs_payload(builder_id=result.builder_id,verified_input_digest=result.verified_input_digest,toolchain_provenance_digest=result.toolchain_provenance_digest,environment_attestation_digest=result.environment_attestation_digest,build_profile=result.build_profile,artifact_digest=result.artifact_digest),hashlib.sha256).hexdigest())
    result.assert_authenticated(builder_key=key,verified_input=verified_input,mir=mir,proof=proof,toolchain=toolchain,toolchain_artifact_bytes=toolchain_artifact_bytes,toolchain_signing_key=toolchain_signing_key,environment=environment,environment_bytes=environment_bytes,workload_bytes=workload_bytes,environment_attestation_key=environment_attestation_key,artifact_bytes=artifact_bytes)
    return result

def _repro_payload(**v)->bytes:
    rows=(f"verified_input={v['verified_input_digest']}",f"artifact={v['artifact_digest']}",f"builder_a={v['builder_a_id']}",f"builder_a_observation={v['builder_a_observation']}",f"builder_a_toolchain={v['builder_a_toolchain']}",f"builder_a_environment={v['builder_a_environment']}",f"builder_b={v['builder_b_id']}",f"builder_b_observation={v['builder_b_observation']}",f"builder_b_toolchain={v['builder_b_toolchain']}",f"builder_b_environment={v['builder_b_environment']}","reproducible=1","authority=0")
    return _REPRO_CTX+"\n".join(rows).encode()

@dataclass(frozen=True,slots=True)
class VerifierReproducibleBuildReceiptV1:
    verified_input_digest:str; artifact_digest:str; builder_a_id:str; builder_a_observation_digest:str; builder_a_toolchain_provenance_digest:str; builder_a_environment_attestation_digest:str; builder_b_id:str; builder_b_observation_digest:str; builder_b_toolchain_provenance_digest:str; builder_b_environment_attestation_digest:str; receipt_digest:str; reproducible:bool=True; authority:bool=False; version:int=1
    def assert_authenticated(self, **k)->None:
        key=_key(k['reproducibility_key'],'reproducibility_key'); a=k['builder_a']; b=k['builder_b']; ea=k['builder_a_environment']; eb=k['builder_b_environment']
        if self.authority or self.reproducible is not True: raise VerifierReproducibleBuildV1Error('reproducible-build receipt must remain non-authoritative and reproducible')
        if a.builder_id==b.builder_id: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct builder identities')
        if ea.environment_id==eb.environment_id or ea.environment_digest==eb.environment_digest: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct attested environments')
        a.assert_authenticated(builder_key=k['builder_a_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k['builder_a_toolchain'],toolchain_artifact_bytes=k['builder_a_toolchain_artifact_bytes'],toolchain_signing_key=k['builder_a_toolchain_signing_key'],environment=ea,environment_bytes=k['builder_a_environment_bytes'],workload_bytes=k['builder_a_workload_bytes'],environment_attestation_key=k['builder_a_environment_attestation_key'],artifact_bytes=k['artifact_bytes'])
        b.assert_authenticated(builder_key=k['builder_b_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k['builder_b_toolchain'],toolchain_artifact_bytes=k['builder_b_toolchain_artifact_bytes'],toolchain_signing_key=k['builder_b_toolchain_signing_key'],environment=eb,environment_bytes=k['builder_b_environment_bytes'],workload_bytes=k['builder_b_workload_bytes'],environment_attestation_key=k['builder_b_environment_attestation_key'],artifact_bytes=k['artifact_bytes'])
        if a.artifact_digest!=b.artifact_digest: raise VerifierReproducibleBuildV1Error('independent builders produced different verifier artifacts')
        expected=(self.verified_input_digest==k['verified_input'].build_input_digest and self.artifact_digest==a.artifact_digest and self.builder_a_id==a.builder_id and self.builder_a_observation_digest==a.observation_digest and self.builder_a_toolchain_provenance_digest==a.toolchain_provenance_digest and self.builder_a_environment_attestation_digest==ea.attestation_digest and self.builder_b_id==b.builder_id and self.builder_b_observation_digest==b.observation_digest and self.builder_b_toolchain_provenance_digest==b.toolchain_provenance_digest and self.builder_b_environment_attestation_digest==eb.attestation_digest)
        if not expected: raise VerifierReproducibleBuildV1Error('reproducible-build receipt binding mismatch')
        digest=hmac.new(key,_repro_payload(verified_input_digest=self.verified_input_digest,artifact_digest=self.artifact_digest,builder_a_id=self.builder_a_id,builder_a_observation=self.builder_a_observation_digest,builder_a_toolchain=self.builder_a_toolchain_provenance_digest,builder_a_environment=self.builder_a_environment_attestation_digest,builder_b_id=self.builder_b_id,builder_b_observation=self.builder_b_observation_digest,builder_b_toolchain=self.builder_b_toolchain_provenance_digest,builder_b_environment=self.builder_b_environment_attestation_digest),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest,digest): raise VerifierReproducibleBuildV1Error('reproducible-build receipt authentication failed')

def seal_reproducible_build_receipt_v1(**k)->VerifierReproducibleBuildReceiptV1:
    a=k['builder_a']; b=k['builder_b']; ea=k['builder_a_environment']; eb=k['builder_b_environment']
    if a.builder_id==b.builder_id: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct builder identities')
    if ea.environment_id==eb.environment_id or ea.environment_digest==eb.environment_digest: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct attested environments')
    a.assert_authenticated(builder_key=k['builder_a_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k['builder_a_toolchain'],toolchain_artifact_bytes=k['builder_a_toolchain_artifact_bytes'],toolchain_signing_key=k['builder_a_toolchain_signing_key'],environment=ea,environment_bytes=k['builder_a_environment_bytes'],workload_bytes=k['builder_a_workload_bytes'],environment_attestation_key=k['builder_a_environment_attestation_key'],artifact_bytes=k['artifact_bytes'])
    b.assert_authenticated(builder_key=k['builder_b_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k['builder_b_toolchain'],toolchain_artifact_bytes=k['builder_b_toolchain_artifact_bytes'],toolchain_signing_key=k['builder_b_toolchain_signing_key'],environment=eb,environment_bytes=k['builder_b_environment_bytes'],workload_bytes=k['builder_b_workload_bytes'],environment_attestation_key=k['builder_b_environment_attestation_key'],artifact_bytes=k['artifact_bytes'])
    if a.artifact_digest!=b.artifact_digest: raise VerifierReproducibleBuildV1Error('independent builders produced different verifier artifacts')
    result=VerifierReproducibleBuildReceiptV1(k['verified_input'].build_input_digest,a.artifact_digest,a.builder_id,a.observation_digest,a.toolchain_provenance_digest,ea.attestation_digest,b.builder_id,b.observation_digest,b.toolchain_provenance_digest,eb.attestation_digest,'')
    key=_key(k['reproducibility_key'],'reproducibility_key')
    object.__setattr__(result,'receipt_digest',hmac.new(key,_repro_payload(verified_input_digest=result.verified_input_digest,artifact_digest=result.artifact_digest,builder_a_id=result.builder_a_id,builder_a_observation=result.builder_a_observation_digest,builder_a_toolchain=result.builder_a_toolchain_provenance_digest,builder_a_environment=result.builder_a_environment_attestation_digest,builder_b_id=result.builder_b_id,builder_b_observation=result.builder_b_observation_digest,builder_b_toolchain=result.builder_b_toolchain_provenance_digest,builder_b_environment=result.builder_b_environment_attestation_digest),hashlib.sha256).hexdigest())
    result.assert_authenticated(**k)
    return result
