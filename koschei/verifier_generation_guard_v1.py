"""Integrity/current guards for reproducible verifier receipts v1.

Historical integrity authenticates the receipt exactly as sealed. Current operational
validity additionally requires builder A/B current trust-anchor generations, live remote
attestation/trust-anchor windows at the trusted runtime epoch, and any downstream-required
distinct-root policy. The compact receipt avoids replaying the whole builder graph.
"""
from __future__ import annotations
import hashlib,hmac
from .trust_anchor_admission_v1 import TrustAnchorGenerationStateV1
from .verifier_reproducible_build_v1 import VerifierReproducibleBuildReceiptV1,_repro_payload

class VerifierGenerationGuardV1Error(ValueError): pass

def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise VerifierGenerationGuardV1Error("reproducibility_key must contain at least 32 bytes")
    return v
def _epoch(v:int)->int:
    if not isinstance(v,int) or isinstance(v,bool) or v<0: raise VerifierGenerationGuardV1Error("current_epoch must be a non-negative integer")
    return v
def _text(v:str,label:str)->str:
    if not isinstance(v,str) or not v.strip(): raise VerifierGenerationGuardV1Error(f"{label} cannot be empty")
    return v.strip()
def _policy(v:bool,label:str)->bool:
    if not isinstance(v,bool): raise VerifierGenerationGuardV1Error(f"{label} must be boolean")
    return v

def _check_window(*,observed:int,expires:int,anchor_start:int,anchor_end:int,current:int|None=None,label:str)->None:
    observed=_epoch(observed); expires=_epoch(expires); anchor_start=_epoch(anchor_start); anchor_end=_epoch(anchor_end)
    if anchor_end<=anchor_start: raise VerifierGenerationGuardV1Error(f"{label} trust-anchor lifetime is invalid")
    if expires<=observed: raise VerifierGenerationGuardV1Error(f"{label} remote-attestation lifetime is invalid")
    if observed<anchor_start or observed>=anchor_end or expires>anchor_end: raise VerifierGenerationGuardV1Error(f"{label} remote-attestation window exceeds trust-anchor lifetime")
    if current is not None and (current<observed or current>=expires or current<anchor_start or current>=anchor_end): raise VerifierGenerationGuardV1Error(f"{label} trust/attestation evidence is not live at current epoch")

def assert_reproducibility_integrity_v1(*,receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes)->None:
    key=_key(reproducibility_key)
    if receipt.authority or receipt.reproducible is not True: raise VerifierGenerationGuardV1Error("reproducibility receipt must remain non-authoritative and reproducible")
    policy=_policy(receipt.require_distinct_trust_roots,"require_distinct_trust_roots")
    root_a=_text(receipt.builder_a_trust_root_id,"builder_a_trust_root_id"); root_b=_text(receipt.builder_b_trust_root_id,"builder_b_trust_root_id")
    if policy and root_a==root_b: raise VerifierGenerationGuardV1Error("reproducibility receipt distinct-root policy is violated")
    _check_window(observed=receipt.builder_a_remote_observed_epoch,expires=receipt.builder_a_remote_expires_before_epoch,anchor_start=receipt.builder_a_trust_anchor_valid_from_epoch,anchor_end=receipt.builder_a_trust_anchor_expires_before_epoch,label="builder A")
    _check_window(observed=receipt.builder_b_remote_observed_epoch,expires=receipt.builder_b_remote_expires_before_epoch,anchor_start=receipt.builder_b_trust_anchor_valid_from_epoch,anchor_end=receipt.builder_b_trust_anchor_expires_before_epoch,label="builder B")
    expected=hmac.new(key,_repro_payload(verified_input_digest=receipt.verified_input_digest,artifact_digest=receipt.artifact_digest,builder_a_id=receipt.builder_a_id,builder_a_observation=receipt.builder_a_observation_digest,builder_a_toolchain=receipt.builder_a_toolchain_provenance_digest,builder_a_environment=receipt.builder_a_environment_attestation_digest,builder_a_remote=receipt.builder_a_remote_attestation_evidence_digest,builder_a_root=root_a,builder_a_remote_observed=receipt.builder_a_remote_observed_epoch,builder_a_remote_expires_before=receipt.builder_a_remote_expires_before_epoch,builder_a_anchor=receipt.builder_a_trust_anchor_id,builder_a_generation=receipt.builder_a_trust_anchor_generation,builder_a_manifest=receipt.builder_a_trust_anchor_manifest_digest,builder_a_anchor_valid_from=receipt.builder_a_trust_anchor_valid_from_epoch,builder_a_anchor_expires_before=receipt.builder_a_trust_anchor_expires_before_epoch,builder_b_id=receipt.builder_b_id,builder_b_observation=receipt.builder_b_observation_digest,builder_b_toolchain=receipt.builder_b_toolchain_provenance_digest,builder_b_environment=receipt.builder_b_environment_attestation_digest,builder_b_remote=receipt.builder_b_remote_attestation_evidence_digest,builder_b_root=root_b,builder_b_remote_observed=receipt.builder_b_remote_observed_epoch,builder_b_remote_expires_before=receipt.builder_b_remote_expires_before_epoch,builder_b_anchor=receipt.builder_b_trust_anchor_id,builder_b_generation=receipt.builder_b_trust_anchor_generation,builder_b_manifest=receipt.builder_b_trust_anchor_manifest_digest,builder_b_anchor_valid_from=receipt.builder_b_trust_anchor_valid_from_epoch,builder_b_anchor_expires_before=receipt.builder_b_trust_anchor_expires_before_epoch,require_distinct_trust_roots=policy),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(receipt.receipt_digest,expected): raise VerifierGenerationGuardV1Error("reproducibility receipt authentication failed")

def assert_reproducibility_current_v1(*,receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes,builder_a_generation_state:TrustAnchorGenerationStateV1,builder_b_generation_state:TrustAnchorGenerationStateV1,current_epoch:int,required_distinct_trust_roots:bool=False)->None:
    assert_reproducibility_integrity_v1(receipt=receipt,reproducibility_key=reproducibility_key)
    current=_epoch(current_epoch); required=_policy(required_distinct_trust_roots,"required_distinct_trust_roots")
    if required and receipt.require_distinct_trust_roots is not True: raise VerifierGenerationGuardV1Error("current verifier policy requires distinct attestation trust roots")
    if required and receipt.builder_a_trust_root_id==receipt.builder_b_trust_root_id: raise VerifierGenerationGuardV1Error("current verifier policy requires distinct attestation trust roots")
    _check_window(observed=receipt.builder_a_remote_observed_epoch,expires=receipt.builder_a_remote_expires_before_epoch,anchor_start=receipt.builder_a_trust_anchor_valid_from_epoch,anchor_end=receipt.builder_a_trust_anchor_expires_before_epoch,current=current,label="builder A")
    _check_window(observed=receipt.builder_b_remote_observed_epoch,expires=receipt.builder_b_remote_expires_before_epoch,anchor_start=receipt.builder_b_trust_anchor_valid_from_epoch,anchor_end=receipt.builder_b_trust_anchor_expires_before_epoch,current=current,label="builder B")
    builder_a_generation_state.assert_current_binding(anchor_id=receipt.builder_a_trust_anchor_id,generation=receipt.builder_a_trust_anchor_generation,manifest_digest=receipt.builder_a_trust_anchor_manifest_digest)
    builder_b_generation_state.assert_current_binding(anchor_id=receipt.builder_b_trust_anchor_id,generation=receipt.builder_b_trust_anchor_generation,manifest_digest=receipt.builder_b_trust_anchor_manifest_digest)
