"""Current trust-generation guard for reproducible verifier receipts v1.

This compact guard authenticates the reproducibility receipt's own HMAC-bound fields and
checks both builder trust-anchor bindings against the caller-supplied current generation
states. It avoids replaying the whole builder proof graph at every provider verification.
"""
from __future__ import annotations
import hashlib,hmac
from .trust_anchor_admission_v1 import TrustAnchorGenerationStateV1
from .verifier_reproducible_build_v1 import VerifierReproducibleBuildReceiptV1,_repro_payload

class VerifierGenerationGuardV1Error(ValueError): pass

def _key(v:bytes)->bytes:
    if not isinstance(v,bytes) or len(v)<32: raise VerifierGenerationGuardV1Error("reproducibility_key must contain at least 32 bytes")
    return v

def assert_reproducibility_current_v1(*,receipt:VerifierReproducibleBuildReceiptV1,reproducibility_key:bytes,builder_a_generation_state:TrustAnchorGenerationStateV1,builder_b_generation_state:TrustAnchorGenerationStateV1)->None:
    key=_key(reproducibility_key)
    if receipt.authority or receipt.reproducible is not True: raise VerifierGenerationGuardV1Error("reproducibility receipt must remain non-authoritative and reproducible")
    expected=hmac.new(key,_repro_payload(
        verified_input_digest=receipt.verified_input_digest,artifact_digest=receipt.artifact_digest,
        builder_a_id=receipt.builder_a_id,builder_a_observation=receipt.builder_a_observation_digest,
        builder_a_toolchain=receipt.builder_a_toolchain_provenance_digest,builder_a_environment=receipt.builder_a_environment_attestation_digest,
        builder_a_remote=receipt.builder_a_remote_attestation_evidence_digest,builder_a_anchor=receipt.builder_a_trust_anchor_id,
        builder_a_generation=receipt.builder_a_trust_anchor_generation,builder_a_manifest=receipt.builder_a_trust_anchor_manifest_digest,
        builder_b_id=receipt.builder_b_id,builder_b_observation=receipt.builder_b_observation_digest,
        builder_b_toolchain=receipt.builder_b_toolchain_provenance_digest,builder_b_environment=receipt.builder_b_environment_attestation_digest,
        builder_b_remote=receipt.builder_b_remote_attestation_evidence_digest,builder_b_anchor=receipt.builder_b_trust_anchor_id,
        builder_b_generation=receipt.builder_b_trust_anchor_generation,builder_b_manifest=receipt.builder_b_trust_anchor_manifest_digest,
    ),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(receipt.receipt_digest,expected): raise VerifierGenerationGuardV1Error("reproducibility receipt authentication failed")
    builder_a_generation_state.assert_current_binding(anchor_id=receipt.builder_a_trust_anchor_id,generation=receipt.builder_a_trust_anchor_generation,manifest_digest=receipt.builder_a_trust_anchor_manifest_digest)
    builder_b_generation_state.assert_current_binding(anchor_id=receipt.builder_b_trust_anchor_id,generation=receipt.builder_b_trust_anchor_generation,manifest_digest=receipt.builder_b_trust_anchor_manifest_digest)
