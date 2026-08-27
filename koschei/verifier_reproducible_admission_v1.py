"""Reproducibility-gated verifier runtime admission for Koschei Lang v1."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .verified_ir_build_input_v1 import VerifiedIrBuildInputV1
from .verifier_build_provenance_v1 import (
    VerifierBuildProvenanceV1,
    VerifierRuntimeAdmissionV1,
    admit_verifier_artifact_v1,
)
from .verifier_reproducible_build_v1 import (
    VerifierBuilderObservationV1,
    VerifierReproducibleBuildReceiptV1,
)

_CTX = b"koschei.verifier-reproducible-runtime-admission/v1\x00"


class VerifierReproducibleAdmissionV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise VerifierReproducibleAdmissionV1Error("reproducible_admission_key must contain at least 32 bytes")
    return value


def _payload(*, base_admission_digest: str, reproducibility_receipt_digest: str,
             verified_input_digest: str, artifact_digest: str,
             adapter_abi_digest: str) -> bytes:
    rows = (
        f"base_admission={base_admission_digest}",
        f"reproducibility={reproducibility_receipt_digest}",
        f"verified_input={verified_input_digest}",
        f"artifact={artifact_digest}",
        f"abi={adapter_abi_digest}",
        "admitted=1",
        "authority=0",
    )
    return _CTX + "\n".join(rows).encode()


@dataclass(frozen=True, slots=True)
class VerifierReproducibleRuntimeAdmissionV1:
    base_runtime_admission_digest: str
    reproducibility_receipt_digest: str
    verified_input_digest: str
    artifact_digest: str
    provider_adapter_abi_digest: str
    admission_digest: str
    admitted: bool = True
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, reproducible_admission_key: bytes,
                             runtime_admission_key: bytes,
                             build_provenance_key: bytes,
                             reproducibility_key: bytes,
                             builder_a_key: bytes,
                             builder_b_key: bytes,
                             base_admission: VerifierRuntimeAdmissionV1,
                             reproducibility_receipt: VerifierReproducibleBuildReceiptV1,
                             builder_a: VerifierBuilderObservationV1,
                             builder_b: VerifierBuilderObservationV1,
                             verified_input: VerifiedIrBuildInputV1,
                             mir: NativeSigilMir,
                             proof: NativeSigilProofBundle,
                             provenance: VerifierBuildProvenanceV1,
                             artifact_bytes: bytes,
                             adapter_abi: ProviderAdapterAbiV1) -> None:
        key = _key(reproducible_admission_key)
        if self.authority or self.admitted is not True:
            raise VerifierReproducibleAdmissionV1Error("reproducible runtime admission must remain non-authoritative and admitted")
        reproducibility_receipt.assert_authenticated(
            reproducibility_key=reproducibility_key,
            builder_a_key=builder_a_key,
            builder_b_key=builder_b_key,
            builder_a=builder_a,
            builder_b=builder_b,
            verified_input=verified_input,
            mir=mir,
            proof=proof,
            artifact_bytes=artifact_bytes,
        )
        base_admission.assert_authenticated(
            runtime_admission_key=runtime_admission_key,
            build_provenance_key=build_provenance_key,
            provenance=provenance,
            artifact_bytes=artifact_bytes,
            adapter_abi=adapter_abi,
        )
        if provenance.build_input_digest != verified_input.build_input_digest:
            raise VerifierReproducibleAdmissionV1Error("build provenance differs from verified reproducible input")
        if reproducibility_receipt.artifact_digest != base_admission.artifact_digest:
            raise VerifierReproducibleAdmissionV1Error("reproducible artifact differs from runtime-admitted artifact")
        expected_fields = (
            (self.base_runtime_admission_digest, base_admission.admission_digest),
            (self.reproducibility_receipt_digest, reproducibility_receipt.receipt_digest),
            (self.verified_input_digest, verified_input.build_input_digest),
            (self.artifact_digest, base_admission.artifact_digest),
            (self.provider_adapter_abi_digest, adapter_abi.abi_digest),
        )
        if any(a != b for a, b in expected_fields):
            raise VerifierReproducibleAdmissionV1Error("reproducible runtime admission binding mismatch")
        expected = hmac.new(key, _payload(
            base_admission_digest=self.base_runtime_admission_digest,
            reproducibility_receipt_digest=self.reproducibility_receipt_digest,
            verified_input_digest=self.verified_input_digest,
            artifact_digest=self.artifact_digest,
            adapter_abi_digest=self.provider_adapter_abi_digest,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.admission_digest, expected):
            raise VerifierReproducibleAdmissionV1Error("reproducible runtime admission authentication failed")


def admit_reproducible_verifier_artifact_v1(*,
    reproducible_admission_key: bytes,
    runtime_admission_key: bytes,
    build_provenance_key: bytes,
    reproducibility_key: bytes,
    builder_a_key: bytes,
    builder_b_key: bytes,
    reproducibility_receipt: VerifierReproducibleBuildReceiptV1,
    builder_a: VerifierBuilderObservationV1,
    builder_b: VerifierBuilderObservationV1,
    verified_input: VerifiedIrBuildInputV1,
    mir: NativeSigilMir,
    proof: NativeSigilProofBundle,
    provenance: VerifierBuildProvenanceV1,
    artifact_bytes: bytes,
    adapter_abi: ProviderAdapterAbiV1,
) -> tuple[VerifierRuntimeAdmissionV1, VerifierReproducibleRuntimeAdmissionV1]:
    reproducibility_receipt.assert_authenticated(
        reproducibility_key=reproducibility_key,
        builder_a_key=builder_a_key,
        builder_b_key=builder_b_key,
        builder_a=builder_a,
        builder_b=builder_b,
        verified_input=verified_input,
        mir=mir,
        proof=proof,
        artifact_bytes=artifact_bytes,
    )
    provenance.assert_from_verified_ir(
        verified_input=verified_input,
        mir=mir,
        proof=proof,
        build_provenance_key=build_provenance_key,
        artifact_bytes=artifact_bytes,
    )
    base = admit_verifier_artifact_v1(
        provenance=provenance,
        artifact_bytes=artifact_bytes,
        adapter_abi=adapter_abi,
        build_provenance_key=build_provenance_key,
        runtime_admission_key=runtime_admission_key,
    )
    key = _key(reproducible_admission_key)
    result = VerifierReproducibleRuntimeAdmissionV1(
        base_runtime_admission_digest=base.admission_digest,
        reproducibility_receipt_digest=reproducibility_receipt.receipt_digest,
        verified_input_digest=verified_input.build_input_digest,
        artifact_digest=base.artifact_digest,
        provider_adapter_abi_digest=adapter_abi.abi_digest,
        admission_digest="",
    )
    object.__setattr__(result, "admission_digest", hmac.new(key, _payload(
        base_admission_digest=result.base_runtime_admission_digest,
        reproducibility_receipt_digest=result.reproducibility_receipt_digest,
        verified_input_digest=result.verified_input_digest,
        artifact_digest=result.artifact_digest,
        adapter_abi_digest=result.provider_adapter_abi_digest,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(
        reproducible_admission_key=key,
        runtime_admission_key=runtime_admission_key,
        build_provenance_key=build_provenance_key,
        reproducibility_key=reproducibility_key,
        builder_a_key=builder_a_key,
        builder_b_key=builder_b_key,
        base_admission=base,
        reproducibility_receipt=reproducibility_receipt,
        builder_a=builder_a,
        builder_b=builder_b,
        verified_input=verified_input,
        mir=mir,
        proof=proof,
        provenance=provenance,
        artifact_bytes=artifact_bytes,
        adapter_abi=adapter_abi,
    )
    return base, result
