"""Verifier artifact build provenance and runtime admission for Koschei Lang v1.

Sanctioned build provenance derives its build-input digest from the sealed Koschei
native IR/proof world and its toolchain identity from authenticated
ToolchainProvenanceV1. Callers cannot select either digest directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import string

from .provider_adapter_abi_v1 import ProviderAdapterAbiV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .toolchain_provenance_v1 import ToolchainProvenanceV1
from .verified_ir_build_input_v1 import VerifiedIrBuildInputV1

_BUILD_CTX = b"koschei.verifier-build-provenance/v1\x00"
_ARTIFACT_CTX = b"koschei.verifier-artifact/v1\x00"
_LOAD_CTX = b"koschei.verifier-runtime-admission/v1\x00"
_HEX = frozenset(string.hexdigits.lower())


class VerifierBuildProvenanceV1Error(ValueError):
    pass


def _key(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise VerifierBuildProvenanceV1Error(f"{label} must contain at least 32 bytes")
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerifierBuildProvenanceV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise VerifierBuildProvenanceV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise VerifierBuildProvenanceV1Error(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def measure_verifier_artifact_v1(artifact_bytes: bytes) -> str:
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise VerifierBuildProvenanceV1Error("artifact_bytes must be non-empty bytes")
    return hashlib.sha256(_ARTIFACT_CTX + artifact_bytes).hexdigest()


def _build_payload(*, artifact_digest: str, build_input_digest: str,
                   toolchain_digest: str, build_profile: str) -> bytes:
    rows = (
        f"artifact={artifact_digest}",
        f"build_input={build_input_digest}",
        f"toolchain={toolchain_digest}",
        f"profile={build_profile}",
        "authority=0",
    )
    return _BUILD_CTX + "\n".join(rows).encode("utf-8")


def _load_payload(*, provenance_digest: str, artifact_digest: str,
                  abi_digest: str) -> bytes:
    rows = (
        f"provenance={provenance_digest}",
        f"artifact={artifact_digest}",
        f"abi={abi_digest}",
        "admitted=1",
        "authority=0",
    )
    return _LOAD_CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class VerifierBuildProvenanceV1:
    artifact_digest: str
    build_input_digest: str
    toolchain_digest: str
    build_profile: str
    provenance_digest: str
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, build_provenance_key: bytes,
                             artifact_bytes: bytes) -> None:
        key = _key(build_provenance_key, "build_provenance_key")
        if self.authority:
            raise VerifierBuildProvenanceV1Error("verifier build provenance cannot carry ambient authority")
        artifact = measure_verifier_artifact_v1(artifact_bytes)
        if artifact != _digest(self.artifact_digest, "artifact_digest"):
            raise VerifierBuildProvenanceV1Error("verifier artifact bytes do not match build provenance")
        build_input = _digest(self.build_input_digest, "build_input_digest")
        toolchain = _digest(self.toolchain_digest, "toolchain_digest")
        profile = _text(self.build_profile, "build_profile")
        expected = hmac.new(key, _build_payload(
            artifact_digest=artifact,
            build_input_digest=build_input,
            toolchain_digest=toolchain,
            build_profile=profile,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.provenance_digest, expected):
            raise VerifierBuildProvenanceV1Error("verifier build provenance authentication failed")

    def assert_from_verified_ir(self, *, verified_input: VerifiedIrBuildInputV1,
                                mir: NativeSigilMir,
                                proof: NativeSigilProofBundle,
                                toolchain: ToolchainProvenanceV1,
                                toolchain_artifact_bytes: bytes,
                                toolchain_signing_key: bytes,
                                build_provenance_key: bytes,
                                artifact_bytes: bytes) -> None:
        verified_input.assert_sealed(mir=mir, proof=proof)
        toolchain.assert_authenticated(
            toolchain_signing_key=toolchain_signing_key,
            toolchain_artifact_bytes=toolchain_artifact_bytes,
        )
        self.assert_authenticated(
            build_provenance_key=build_provenance_key,
            artifact_bytes=artifact_bytes,
        )
        if self.build_input_digest != verified_input.build_input_digest:
            raise VerifierBuildProvenanceV1Error(
                "verifier build provenance does not derive from supplied verified IR input"
            )
        if self.toolchain_digest != toolchain.provenance_digest:
            raise VerifierBuildProvenanceV1Error(
                "verifier build provenance does not derive from supplied signed toolchain"
            )


def _attest_verifier_build_digest_v1(*, artifact_bytes: bytes,
                                     build_input_digest: str,
                                     toolchain_digest: str,
                                     build_profile: str,
                                     build_provenance_key: bytes) -> VerifierBuildProvenanceV1:
    key = _key(build_provenance_key, "build_provenance_key")
    artifact = measure_verifier_artifact_v1(artifact_bytes)
    build_input = _digest(build_input_digest, "build_input_digest")
    toolchain_digest = _digest(toolchain_digest, "toolchain_digest")
    profile = _text(build_profile, "build_profile")
    result = VerifierBuildProvenanceV1(
        artifact_digest=artifact,
        build_input_digest=build_input,
        toolchain_digest=toolchain_digest,
        build_profile=profile,
        provenance_digest="",
    )
    object.__setattr__(result, "provenance_digest", hmac.new(key, _build_payload(
        artifact_digest=artifact,
        build_input_digest=build_input,
        toolchain_digest=toolchain_digest,
        build_profile=profile,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(build_provenance_key=key, artifact_bytes=artifact_bytes)
    return result


def attest_verifier_build_from_verified_ir_v1(*,
                                               verified_input: VerifiedIrBuildInputV1,
                                               mir: NativeSigilMir,
                                               proof: NativeSigilProofBundle,
                                               artifact_bytes: bytes,
                                               toolchain: ToolchainProvenanceV1,
                                               toolchain_artifact_bytes: bytes,
                                               toolchain_signing_key: bytes,
                                               build_profile: str,
                                               build_provenance_key: bytes) -> VerifierBuildProvenanceV1:
    """Sanctioned build attestation: build input and toolchain identity are inherited."""
    verified_input.assert_sealed(mir=mir, proof=proof)
    toolchain.assert_authenticated(
        toolchain_signing_key=toolchain_signing_key,
        toolchain_artifact_bytes=toolchain_artifact_bytes,
    )
    result = _attest_verifier_build_digest_v1(
        artifact_bytes=artifact_bytes,
        build_input_digest=verified_input.build_input_digest,
        toolchain_digest=toolchain.provenance_digest,
        build_profile=build_profile,
        build_provenance_key=build_provenance_key,
    )
    result.assert_from_verified_ir(
        verified_input=verified_input,
        mir=mir,
        proof=proof,
        toolchain=toolchain,
        toolchain_artifact_bytes=toolchain_artifact_bytes,
        toolchain_signing_key=toolchain_signing_key,
        build_provenance_key=build_provenance_key,
        artifact_bytes=artifact_bytes,
    )
    return result


@dataclass(frozen=True, slots=True)
class VerifierRuntimeAdmissionV1:
    build_provenance_digest: str
    artifact_digest: str
    provider_adapter_abi_digest: str
    admission_digest: str
    admitted: bool = True
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, runtime_admission_key: bytes,
                             build_provenance_key: bytes,
                             provenance: VerifierBuildProvenanceV1,
                             artifact_bytes: bytes,
                             adapter_abi: ProviderAdapterAbiV1) -> None:
        key = _key(runtime_admission_key, "runtime_admission_key")
        if self.authority or self.admitted is not True:
            raise VerifierBuildProvenanceV1Error("verifier runtime admission must remain non-authoritative and admitted")
        provenance.assert_authenticated(build_provenance_key=build_provenance_key, artifact_bytes=artifact_bytes)
        adapter_abi.assert_sealed()
        measured = measure_verifier_artifact_v1(artifact_bytes)
        if measured != adapter_abi.verifier_implementation_digest:
            raise VerifierBuildProvenanceV1Error("loaded verifier artifact differs from adapter ABI implementation digest")
        if provenance.artifact_digest != adapter_abi.verifier_implementation_digest:
            raise VerifierBuildProvenanceV1Error("build provenance artifact differs from adapter ABI implementation digest")
        if self.build_provenance_digest != provenance.provenance_digest:
            raise VerifierBuildProvenanceV1Error("runtime admission build provenance mismatch")
        if self.artifact_digest != measured:
            raise VerifierBuildProvenanceV1Error("runtime admission artifact digest mismatch")
        if self.provider_adapter_abi_digest != adapter_abi.abi_digest:
            raise VerifierBuildProvenanceV1Error("runtime admission adapter ABI mismatch")
        expected = hmac.new(key, _load_payload(
            provenance_digest=self.build_provenance_digest,
            artifact_digest=self.artifact_digest,
            abi_digest=self.provider_adapter_abi_digest,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.admission_digest, expected):
            raise VerifierBuildProvenanceV1Error("verifier runtime admission authentication failed")


def admit_verifier_artifact_v1(*, provenance: VerifierBuildProvenanceV1,
                               artifact_bytes: bytes,
                               adapter_abi: ProviderAdapterAbiV1,
                               build_provenance_key: bytes,
                               runtime_admission_key: bytes) -> VerifierRuntimeAdmissionV1:
    runtime_key = _key(runtime_admission_key, "runtime_admission_key")
    provenance.assert_authenticated(build_provenance_key=build_provenance_key, artifact_bytes=artifact_bytes)
    adapter_abi.assert_sealed()
    measured = measure_verifier_artifact_v1(artifact_bytes)
    if measured != adapter_abi.verifier_implementation_digest:
        raise VerifierBuildProvenanceV1Error("loaded verifier artifact differs from adapter ABI implementation digest")
    result = VerifierRuntimeAdmissionV1(
        build_provenance_digest=provenance.provenance_digest,
        artifact_digest=measured,
        provider_adapter_abi_digest=adapter_abi.abi_digest,
        admission_digest="",
    )
    object.__setattr__(result, "admission_digest", hmac.new(runtime_key, _load_payload(
        provenance_digest=result.build_provenance_digest,
        artifact_digest=result.artifact_digest,
        abi_digest=result.provider_adapter_abi_digest,
    ), hashlib.sha256).hexdigest())
    result.assert_authenticated(
        runtime_admission_key=runtime_key,
        build_provenance_key=build_provenance_key,
        provenance=provenance,
        artifact_bytes=artifact_bytes,
        adapter_abi=adapter_abi,
    )
    return result
