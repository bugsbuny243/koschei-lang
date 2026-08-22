"""End-to-end proof sealing for native Koschei sigil programs v1.

This module closes the compiler-to-proof chain without fabricating subsystem
evidence. A caller supplies completed LibraryProofReceipt values produced by the
real Library subsystems (or by explicit test fixtures). The pipeline verifies the
sealed native MIR, derives the exact Library plan committed by that MIR, seals
all receipts against that plan, and binds the final proof envelope back to the
compiler product.

Source text is intentionally absent from this layer: once compilation produced
sealed native MIR, later stages consume only the committed semantic product.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .library_proof_envelope_v1 import (
    LibraryProofEnvelope,
    LibraryProofReceipt,
    require_library_proof_envelope,
    seal_library_proof_envelope,
)
from .native_sigil_library_bridge_v1 import (
    NativeSigilLibraryPlan,
    expand_native_sigil_mir,
)
from .native_sigil_mir_v1 import NativeSigilMir

_CTX = b"koschei.native-sigil-proof-pipeline/v1\x00"


class NativeSigilProofPipelineError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NativeSigilProofBundle:
    native_mir_fingerprint: str
    universe_plan_digest: str
    native_library_plan_digest: str
    library_proof: LibraryProofEnvelope
    decision: str
    digest: str
    version: int = 1

    def assert_sealed(self, plan: NativeSigilLibraryPlan) -> None:
        if self.native_mir_fingerprint != plan.native_mir_fingerprint:
            raise NativeSigilProofPipelineError("proof bundle MIR fingerprint mismatch")
        if self.universe_plan_digest != plan.universe_plan_digest:
            raise NativeSigilProofPipelineError("proof bundle Universe identity mismatch")
        if self.native_library_plan_digest != plan.digest:
            raise NativeSigilProofPipelineError("proof bundle Library-plan identity mismatch")

        require_library_proof_envelope(plan.library_plan, self.library_proof)
        if self.decision != self.library_proof.decision:
            raise NativeSigilProofPipelineError("proof bundle decision mismatch")

        expected = _bundle_digest(
            self.native_mir_fingerprint,
            self.universe_plan_digest,
            self.native_library_plan_digest,
            self.library_proof.digest,
            self.decision,
        )
        if self.digest != expected:
            raise NativeSigilProofPipelineError("native sigil proof bundle seal mismatch")


def _bundle_digest(
    mir_fingerprint: str,
    universe_digest: str,
    native_library_digest: str,
    proof_digest: str,
    decision: str,
) -> str:
    payload = "\n".join(
        (
            f"mir={mir_fingerprint}",
            f"universe={universe_digest}",
            f"native-library={native_library_digest}",
            f"proof={proof_digest}",
            f"decision={decision}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def seal_native_sigil_proof(
    mir: NativeSigilMir,
    receipts: Iterable[LibraryProofReceipt],
) -> NativeSigilProofBundle:
    """Seal real Library evidence to the exact compiler-produced native MIR."""

    mir.assert_sealed()
    plan = expand_native_sigil_mir(mir)
    plan.assert_sealed()

    proof = seal_library_proof_envelope(plan.library_plan, receipts)
    require_library_proof_envelope(plan.library_plan, proof)

    result = NativeSigilProofBundle(
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        native_library_plan_digest=plan.digest,
        library_proof=proof,
        decision=proof.decision,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _bundle_digest(
            result.native_mir_fingerprint,
            result.universe_plan_digest,
            result.native_library_plan_digest,
            proof.digest,
            result.decision,
        ),
    )
    result.assert_sealed(plan)
    return result


def require_native_sigil_proof(
    mir: NativeSigilMir,
    bundle: NativeSigilProofBundle,
) -> NativeSigilLibraryPlan:
    """Re-derive the canonical plan and verify a proof bundle before enforcement."""

    mir.assert_sealed()
    plan = expand_native_sigil_mir(mir)
    bundle.assert_sealed(plan)
    return plan
