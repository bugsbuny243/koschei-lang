"""Independent verifier reproducible-build verification for Koschei Lang v1."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac
from .builder_environment_attestation_v1 import BuilderEnvironmentAttestationV1
from .remote_attestation_evidence_v1 import RemoteAttestationEvidenceV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .toolchain_provenance_v1 import ToolchainProvenanceV1
from .verified_ir_build_input_v1 import VerifiedIrBuildInputV1

_OBS_CTX=b"koschei.verifier-builder-observation/v1\x00"; _REPRO_CTX=b"koschei.verifier-reproducible-build/v1\x00"; _ARTIFACT_CTX=b"koschei.verifier-artifact/v1\x00"
class VerifierReproducibleBuildV1Error(ValueError): pass
def _key(v,l):
    if not isinstance(v,bytes) or len(v)<32: raise VerifierReproducibleBuildV1Error(f"{l} must contain at least 32 bytes")
    return v
def _text(v,l):
    if not isinstance(v,str) or not v.strip(): raise VerifierReproducibleBuildV1Error(f"{l} cannot be empty")
    return v.strip()
def _generation(v):
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise VerifierReproducibleBuildV1Error("trust-anchor generation must be a non-negative integer")
    return v
def _measure(b):
    if not isinstance(b,bytes) or not b: raise VerifierReproducibleBuildV1Error("artifact_bytes must be non-empty bytes")
    return hashlib.sha256(_ARTIFACT_CTX+b).hexdigest()
def _obs_payload(**v):
    rows=(f"builder={v['builder_id']}",f"verified_input={v['verified_input_digest']}",f"toolchain={v['toolchain_provenance_digest']}",f"environment={v['environment_attestation_digest']}",f"remote={v['remote_attestation_evidence_digest']}",f"trust_anchor_id={v['trust_anchor_id']}",f"trust_anchor_generation={v['trust_anchor_generation']}",f"trust_anchor_manifest={v['trust_anchor_manifest_digest']}",f"profile={v['build_profile']}",f"artifact={v['artifact_digest']}","authority=0")
    return _OBS_CTX+"\n".join(rows).encode()

@dataclass(frozen=True,slots=True)
class VerifierBuilderObservationV1:
    builder_id:str; verified_input_digest:str; toolchain_provenance_digest:str; environment_attestation_digest:str; remote_attestation_evidence_digest:str; trust_anchor_id:str; trust_anchor_generation:int; trust_anchor_manifest_digest:str; build_profile:str; artifact_digest:str; observation_digest:str; authority:bool=False; version:int=1
    def assert_authenticated(self,**k):
        key=_key(k['builder_key'],'builder_key'); k['verified_input'].assert_sealed(mir=k['mir'],proof=k['proof'])
        k['toolchain'].assert_authenticated(toolchain_signing_key=k['toolchain_signing_key'],toolchain_artifact_bytes=k['toolchain_artifact_bytes'])
        k['environment'].assert_authenticated(environment_attestation_key=k['environment_attestation_key'],environment_bytes=k['environment_bytes'],workload_bytes=k['workload_bytes'],remote_evidence=k['remote_evidence'],raw_remote_evidence_bytes=k['raw_remote_evidence_bytes'],remote_attestation_verifier_key=k['remote_attestation_verifier_key'],current_epoch=k['current_epoch'],trust_anchor_generation_state=k['trust_anchor_generation_state'])
        if self.authority: raise VerifierReproducibleBuildV1Error('builder observation cannot carry ambient authority')
        if self.builder_id!=k['environment'].builder_id: raise VerifierReproducibleBuildV1Error('builder observation environment builder mismatch')
        r=k['remote_evidence']; expected=(self.verified_input_digest==k['verified_input'].build_input_digest and self.toolchain_provenance_digest==k['toolchain'].provenance_digest and self.environment_attestation_digest==k['environment'].attestation_digest and self.remote_attestation_evidence_digest==r.evidence_digest and self.trust_anchor_id==r.trust_anchor_id and self.trust_anchor_generation==r.trust_anchor_generation and self.trust_anchor_manifest_digest==r.trust_anchor_manifest_digest and self.artifact_digest==_measure(k['artifact_bytes']))
        if not expected: raise VerifierReproducibleBuildV1Error('builder observation binding mismatch')
        digest=hmac.new(key,_obs_payload(builder_id=_text(self.builder_id,'builder_id'),verified_input_digest=self.verified_input_digest,toolchain_provenance_digest=self.toolchain_provenance_digest,environment_attestation_digest=self.environment_attestation_digest,remote_attestation_evidence_digest=self.remote_attestation_evidence_digest,trust_anchor_id=_text(self.trust_anchor_id,'trust_anchor_id'),trust_anchor_generation=_generation(self.trust_anchor_generation),trust_anchor_manifest_digest=_text(self.trust_anchor_manifest_digest,'trust_anchor_manifest_digest'),build_profile=_text(self.build_profile,'build_profile'),artifact_digest=self.artifact_digest),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.observation_digest,digest): raise VerifierReproducibleBuildV1Error('builder observation authentication failed')

def attest_builder_observation_v1(**k):
    key=_key(k['builder_key'],'builder_key'); k['verified_input'].assert_sealed(mir=k['mir'],proof=k['proof'])
    k['toolchain'].assert_authenticated(toolchain_signing_key=k['toolchain_signing_key'],toolchain_artifact_bytes=k['toolchain_artifact_bytes'])
    k['environment'].assert_authenticated(environment_attestation_key=k['environment_attestation_key'],environment_bytes=k['environment_bytes'],workload_bytes=k['workload_bytes'],remote_evidence=k['remote_evidence'],raw_remote_evidence_bytes=k['raw_remote_evidence_bytes'],remote_attestation_verifier_key=k['remote_attestation_verifier_key'],current_epoch=k['current_epoch'],trust_anchor_generation_state=k['trust_anchor_generation_state'])
    if k['builder_id']!=k['environment'].builder_id: raise VerifierReproducibleBuildV1Error('builder observation environment builder mismatch')
    remote=k['remote_evidence']; r=VerifierBuilderObservationV1(_text(k['builder_id'],'builder_id'),k['verified_input'].build_input_digest,k['toolchain'].provenance_digest,k['environment'].attestation_digest,remote.evidence_digest,remote.trust_anchor_id,remote.trust_anchor_generation,remote.trust_anchor_manifest_digest,_text(k['build_profile'],'build_profile'),_measure(k['artifact_bytes']),'')
    object.__setattr__(r,'observation_digest',hmac.new(key,_obs_payload(builder_id=r.builder_id,verified_input_digest=r.verified_input_digest,toolchain_provenance_digest=r.toolchain_provenance_digest,environment_attestation_digest=r.environment_attestation_digest,remote_attestation_evidence_digest=r.remote_attestation_evidence_digest,trust_anchor_id=r.trust_anchor_id,trust_anchor_generation=r.trust_anchor_generation,trust_anchor_manifest_digest=r.trust_anchor_manifest_digest,build_profile=r.build_profile,artifact_digest=r.artifact_digest),hashlib.sha256).hexdigest()); r.assert_authenticated(**k); return r

def _repro_payload(**v):
    rows=(f"verified_input={v['verified_input_digest']}",f"artifact={v['artifact_digest']}",f"builder_a={v['builder_a_id']}",f"builder_a_observation={v['builder_a_observation']}",f"builder_a_toolchain={v['builder_a_toolchain']}",f"builder_a_environment={v['builder_a_environment']}",f"builder_a_remote={v['builder_a_remote']}",f"builder_a_anchor={v['builder_a_anchor']}",f"builder_a_generation={v['builder_a_generation']}",f"builder_a_manifest={v['builder_a_manifest']}",f"builder_b={v['builder_b_id']}",f"builder_b_observation={v['builder_b_observation']}",f"builder_b_toolchain={v['builder_b_toolchain']}",f"builder_b_environment={v['builder_b_environment']}",f"builder_b_remote={v['builder_b_remote']}",f"builder_b_anchor={v['builder_b_anchor']}",f"builder_b_generation={v['builder_b_generation']}",f"builder_b_manifest={v['builder_b_manifest']}","reproducible=1","authority=0")
    return _REPRO_CTX+"\n".join(rows).encode()

@dataclass(frozen=True,slots=True)
class VerifierReproducibleBuildReceiptV1:
    verified_input_digest:str; artifact_digest:str; builder_a_id:str; builder_a_observation_digest:str; builder_a_toolchain_provenance_digest:str; builder_a_environment_attestation_digest:str; builder_a_remote_attestation_evidence_digest:str; builder_a_trust_anchor_id:str; builder_a_trust_anchor_generation:int; builder_a_trust_anchor_manifest_digest:str; builder_b_id:str; builder_b_observation_digest:str; builder_b_toolchain_provenance_digest:str; builder_b_environment_attestation_digest:str; builder_b_remote_attestation_evidence_digest:str; builder_b_trust_anchor_id:str; builder_b_trust_anchor_generation:int; builder_b_trust_anchor_manifest_digest:str; receipt_digest:str; reproducible:bool=True; authority:bool=False; version:int=1
    def assert_authenticated(self,**k):
        key=_key(k['reproducibility_key'],'reproducibility_key'); a=k['builder_a']; b=k['builder_b']; ea=k['builder_a_environment']; eb=k['builder_b_environment']; ra=k['builder_a_remote_evidence']; rb=k['builder_b_remote_evidence']
        if self.authority or self.reproducible is not True: raise VerifierReproducibleBuildV1Error('reproducible-build receipt must remain non-authoritative and reproducible')
        if a.builder_id==b.builder_id: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct builder identities')
        if ea.environment_id==eb.environment_id or ea.environment_digest==eb.environment_digest: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct attested environments')
        if k.get('require_distinct_trust_roots',False) and ra.trust_root_id==rb.trust_root_id: raise VerifierReproducibleBuildV1Error('reproducible build policy requires distinct attestation trust roots')
        for prefix,obs,env,remote in [('builder_a',a,ea,ra),('builder_b',b,eb,rb)]:
            obs.assert_authenticated(builder_key=k[prefix+'_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k[prefix+'_toolchain'],toolchain_artifact_bytes=k[prefix+'_toolchain_artifact_bytes'],toolchain_signing_key=k[prefix+'_toolchain_signing_key'],environment=env,environment_bytes=k[prefix+'_environment_bytes'],workload_bytes=k[prefix+'_workload_bytes'],environment_attestation_key=k[prefix+'_environment_attestation_key'],remote_evidence=remote,raw_remote_evidence_bytes=k[prefix+'_raw_remote_evidence_bytes'],remote_attestation_verifier_key=k[prefix+'_remote_attestation_verifier_key'],current_epoch=k['current_epoch'],trust_anchor_generation_state=k[prefix+'_trust_anchor_generation_state'],artifact_bytes=k['artifact_bytes'])
        if a.artifact_digest!=b.artifact_digest: raise VerifierReproducibleBuildV1Error('independent builders produced different verifier artifacts')
        expected=(self.verified_input_digest==k['verified_input'].build_input_digest and self.artifact_digest==a.artifact_digest and self.builder_a_observation_digest==a.observation_digest and self.builder_b_observation_digest==b.observation_digest and self.builder_a_remote_attestation_evidence_digest==ra.evidence_digest and self.builder_b_remote_attestation_evidence_digest==rb.evidence_digest and self.builder_a_trust_anchor_id==ra.trust_anchor_id and self.builder_a_trust_anchor_generation==ra.trust_anchor_generation and self.builder_a_trust_anchor_manifest_digest==ra.trust_anchor_manifest_digest and self.builder_b_trust_anchor_id==rb.trust_anchor_id and self.builder_b_trust_anchor_generation==rb.trust_anchor_generation and self.builder_b_trust_anchor_manifest_digest==rb.trust_anchor_manifest_digest)
        if not expected: raise VerifierReproducibleBuildV1Error('reproducible-build receipt binding mismatch')
        digest=hmac.new(key,_repro_payload(verified_input_digest=self.verified_input_digest,artifact_digest=self.artifact_digest,builder_a_id=self.builder_a_id,builder_a_observation=self.builder_a_observation_digest,builder_a_toolchain=self.builder_a_toolchain_provenance_digest,builder_a_environment=self.builder_a_environment_attestation_digest,builder_a_remote=self.builder_a_remote_attestation_evidence_digest,builder_a_anchor=self.builder_a_trust_anchor_id,builder_a_generation=_generation(self.builder_a_trust_anchor_generation),builder_a_manifest=self.builder_a_trust_anchor_manifest_digest,builder_b_id=self.builder_b_id,builder_b_observation=self.builder_b_observation_digest,builder_b_toolchain=self.builder_b_toolchain_provenance_digest,builder_b_environment=self.builder_b_environment_attestation_digest,builder_b_remote=self.builder_b_remote_attestation_evidence_digest,builder_b_anchor=self.builder_b_trust_anchor_id,builder_b_generation=_generation(self.builder_b_trust_anchor_generation),builder_b_manifest=self.builder_b_trust_anchor_manifest_digest),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.receipt_digest,digest): raise VerifierReproducibleBuildV1Error('reproducible-build receipt authentication failed')

def seal_reproducible_build_receipt_v1(**k):
    a=k['builder_a']; b=k['builder_b']; ea=k['builder_a_environment']; eb=k['builder_b_environment']; ra=k['builder_a_remote_evidence']; rb=k['builder_b_remote_evidence']
    if a.builder_id==b.builder_id: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct builder identities')
    if ea.environment_id==eb.environment_id or ea.environment_digest==eb.environment_digest: raise VerifierReproducibleBuildV1Error('reproducible build requires distinct attested environments')
    if k.get('require_distinct_trust_roots',False) and ra.trust_root_id==rb.trust_root_id: raise VerifierReproducibleBuildV1Error('reproducible build policy requires distinct attestation trust roots')
    for prefix,obs,env,remote in [('builder_a',a,ea,ra),('builder_b',b,eb,rb)]:
        obs.assert_authenticated(builder_key=k[prefix+'_key'],verified_input=k['verified_input'],mir=k['mir'],proof=k['proof'],toolchain=k[prefix+'_toolchain'],toolchain_artifact_bytes=k[prefix+'_toolchain_artifact_bytes'],toolchain_signing_key=k[prefix+'_toolchain_signing_key'],environment=env,environment_bytes=k[prefix+'_environment_bytes'],workload_bytes=k[prefix+'_workload_bytes'],environment_attestation_key=k[prefix+'_environment_attestation_key'],remote_evidence=remote,raw_remote_evidence_bytes=k[prefix+'_raw_remote_evidence_bytes'],remote_attestation_verifier_key=k[prefix+'_remote_attestation_verifier_key'],current_epoch=k['current_epoch'],trust_anchor_generation_state=k[prefix+'_trust_anchor_generation_state'],artifact_bytes=k['artifact_bytes'])
    if a.artifact_digest!=b.artifact_digest: raise VerifierReproducibleBuildV1Error('independent builders produced different verifier artifacts')
    r=VerifierReproducibleBuildReceiptV1(k['verified_input'].build_input_digest,a.artifact_digest,a.builder_id,a.observation_digest,a.toolchain_provenance_digest,ea.attestation_digest,ra.evidence_digest,ra.trust_anchor_id,ra.trust_anchor_generation,ra.trust_anchor_manifest_digest,b.builder_id,b.observation_digest,b.toolchain_provenance_digest,eb.attestation_digest,rb.evidence_digest,rb.trust_anchor_id,rb.trust_anchor_generation,rb.trust_anchor_manifest_digest,'')
    key=_key(k['reproducibility_key'],'reproducibility_key'); object.__setattr__(r,'receipt_digest',hmac.new(key,_repro_payload(verified_input_digest=r.verified_input_digest,artifact_digest=r.artifact_digest,builder_a_id=r.builder_a_id,builder_a_observation=r.builder_a_observation_digest,builder_a_toolchain=r.builder_a_toolchain_provenance_digest,builder_a_environment=r.builder_a_environment_attestation_digest,builder_a_remote=r.builder_a_remote_attestation_evidence_digest,builder_a_anchor=r.builder_a_trust_anchor_id,builder_a_generation=r.builder_a_trust_anchor_generation,builder_a_manifest=r.builder_a_trust_anchor_manifest_digest,builder_b_id=r.builder_b_id,builder_b_observation=r.builder_b_observation_digest,builder_b_toolchain=r.builder_b_toolchain_provenance_digest,builder_b_environment=r.builder_b_environment_attestation_digest,builder_b_remote=r.builder_b_remote_attestation_evidence_digest,builder_b_anchor=r.builder_b_trust_anchor_id,builder_b_generation=r.builder_b_trust_anchor_generation,builder_b_manifest=r.builder_b_trust_anchor_manifest_digest),hashlib.sha256).hexdigest()); r.assert_authenticated(**k); return r
