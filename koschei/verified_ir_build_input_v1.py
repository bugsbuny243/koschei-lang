"""Canonical verifier build-input identity derived from sealed Koschei native IR v1.

This module does not invent a second IR. It derives one non-authoritative build-input
identity from the existing sealed NativeSigilMir plus NativeSigilProofBundle. The
result can be used by build provenance so callers cannot inject an arbitrary
`build_input_digest` and later claim the verifier artifact came from Koschei's
verified semantic world.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle, require_native_sigil_proof

_CTX = b"koschei.verified-ir-build-input/v1\x00"


class VerifiedIrBuildInputV1Error(ValueError):
    pass


def _identity_digest(mir: NativeSigilMir, proof: NativeSigilProofBundle) -> str:
    rows = (
        f"native_mir={mir.fingerprint}",
        f"universe={mir.universe_plan_digest}",
        f"native_proof={proof.digest}",
        f"library_proof={proof.library_proof.digest}",
        f"decision={proof.decision}",
        "authority=0",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VerifiedIrBuildInputV1:
    native_mir_fingerprint: str
    universe_plan_digest: str
    native_proof_digest: str
    library_proof_digest: str
    proof_decision: str
    build_input_digest: str
    authority: bool = False
    version: int = 1

    def assert_sealed(self, *, mir: NativeSigilMir, proof: NativeSigilProofBundle) -> None:
        if self.authority:
            raise VerifiedIrBuildInputV1Error("verified IR build input cannot carry ambient authority")
        require_native_sigil_proof(mir, proof)
        expected_fields = (
            (self.native_mir_fingerprint, mir.fingerprint, "native MIR"),
            (self.universe_plan_digest, mir.universe_plan_digest, "Universe"),
            (self.native_proof_digest, proof.digest, "native proof"),
            (self.library_proof_digest, proof.library_proof.digest, "Library proof"),
            (self.proof_decision, proof.decision, "proof decision"),
        )
        for actual, expected, label in expected_fields:
            if actual != expected:
                raise VerifiedIrBuildInputV1Error(f"verified IR build-input {label} mismatch")
        expected_digest = _identity_digest(mir, proof)
        if self.build_input_digest != expected_digest:
            raise VerifiedIrBuildInputV1Error("verified IR build-input digest mismatch")


def derive_verified_ir_build_input_v1(*, mir: NativeSigilMir,
                                      proof: NativeSigilProofBundle) -> VerifiedIrBuildInputV1:
    """Derive build-input identity only from the existing sealed native compiler/proof chain."""
    require_native_sigil_proof(mir, proof)
    result = VerifiedIrBuildInputV1(
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        native_proof_digest=proof.digest,
        library_proof_digest=proof.library_proof.digest,
        proof_decision=proof.decision,
        build_input_digest=_identity_digest(mir, proof),
    )
    result.assert_sealed(mir=mir, proof=proof)
    return result
