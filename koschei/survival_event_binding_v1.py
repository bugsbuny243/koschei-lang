"""Bind a survival-branch decision to one exact Galaxy event v1.

A survival decision is only a plan commitment.  It must never become reusable
ambient authority.  This module binds the chosen branch/action to one exact
Aevra, Veyra, Matrix, Hara, native-MIR reality, canonical request, Sathra and
epoch.  The chosen branch's action commitment must equal the canonical action
commitment derived from that exact event.

Nothing here executes an effect or manufactures authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_sathra_v1 import Sathra
from .matrix_reality_v1 import HaraIdentity, MatrixAdmission, MatrixIdentity
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest
from .sathra_request_binding_v1 import SathraRequestBinding
from .survival_branch_v1 import SurvivalBranch, SurvivalBranchDecision

_CTX = b"koschei.survival-event-binding/v1\x00"


class SurvivalEventBindingError(ValueError):
    pass


def survival_action_commitment(
    *,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    matrix: MatrixIdentity,
    hara: HaraIdentity,
    request: CanonicalEffectRequest,
) -> str:
    """Canonical plan commitment for one exact prospective Galaxy action."""

    try:
        mir.assert_sealed()
        veyra.assert_sealed()
        aevra.assert_sealed(veyra, mir)
        matrix.assert_sealed(veyra)
        hara.assert_sealed(matrix, veyra, aevra, mir)
        request.assert_sealed(mir)
    except ValueError as error:
        raise SurvivalEventBindingError(str(error)) from error
    if request.epoch != hara.epoch:
        raise SurvivalEventBindingError("survival action request/Hara epoch mismatch")
    rows = (
        f"mir={mir.fingerprint}",
        f"veyra={veyra.digest}",
        f"aevra={aevra.digest}",
        f"matrix={matrix.digest}",
        f"hara={hara.digest}",
        f"request={request.digest}",
        f"epoch={request.epoch}",
    )
    return hashlib.sha256(_CTX + b"action\x00" + "\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SurvivalEventBinding:
    decision_digest: str
    branch_digest: str
    action_commitment_digest: str
    request_digest: str
    sathra_digest: str
    sathra_binding_digest: str
    aevra_digest: str
    veyra_digest: str
    matrix_digest: str
    hara_digest: str
    native_mir_fingerprint: str
    epoch: int
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        *,
        decision: SurvivalBranchDecision,
        branch: SurvivalBranch,
        mir: NativeSigilMir,
        veyra: VeyraIdentity,
        aevra: AevraIdentity,
        matrix: MatrixIdentity,
        hara: HaraIdentity,
        matrix_admission: MatrixAdmission,
        request: CanonicalEffectRequest,
        sathra: Sathra,
        sathra_binding: SathraRequestBinding,
    ) -> None:
        try:
            decision.assert_sealed()
            matrix_admission.assert_sealed(matrix, hara, veyra, aevra, mir)
            request.assert_sealed(mir)
            sathra.assert_sealed()
            sathra_binding.assert_sealed(mir, veyra, aevra, request, sathra)
        except ValueError as error:
            raise SurvivalEventBindingError(str(error)) from error

        canonical_action = survival_action_commitment(
            mir=mir,
            veyra=veyra,
            aevra=aevra,
            matrix=matrix,
            hara=hara,
            request=request,
        )
        if decision.chosen_branch_digest != branch.branch_digest:
            raise SurvivalEventBindingError("survival decision/branch mismatch")
        if decision.chosen_action_commitment_digest != branch.action_commitment_digest:
            raise SurvivalEventBindingError("survival decision/action mismatch")
        if branch.action_commitment_digest != canonical_action:
            raise SurvivalEventBindingError("chosen survival action is not bound to this exact Galaxy event")
        if sathra.event_digest != request.digest:
            raise SurvivalEventBindingError("survival event Sathra/request mismatch")
        if sathra.aevra_digest != aevra.digest or sathra.veyra_digest != veyra.digest:
            raise SurvivalEventBindingError("survival event Sathra identity mismatch")
        if sathra.reality_digest != mir.fingerprint or sathra.epoch != request.epoch:
            raise SurvivalEventBindingError("survival event Sathra reality/epoch mismatch")
        if matrix_admission.epoch != request.epoch:
            raise SurvivalEventBindingError("survival event Matrix/Hara epoch mismatch")

        expected = _binding_digest(
            decision_digest=decision.digest,
            branch_digest=branch.branch_digest,
            action_commitment_digest=canonical_action,
            request_digest=request.digest,
            sathra_digest=sathra.digest,
            sathra_binding_digest=sathra_binding.digest,
            aevra_digest=aevra.digest,
            veyra_digest=veyra.digest,
            matrix_digest=matrix.digest,
            hara_digest=hara.digest,
            native_mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
        )
        expected_fields = (
            (self.decision_digest, decision.digest, "decision"),
            (self.branch_digest, branch.branch_digest, "branch"),
            (self.action_commitment_digest, canonical_action, "action"),
            (self.request_digest, request.digest, "request"),
            (self.sathra_digest, sathra.digest, "Sathra"),
            (self.sathra_binding_digest, sathra_binding.digest, "Sathra binding"),
            (self.aevra_digest, aevra.digest, "Aevra"),
            (self.veyra_digest, veyra.digest, "Veyra"),
            (self.matrix_digest, matrix.digest, "Matrix"),
            (self.hara_digest, hara.digest, "Hara"),
            (self.native_mir_fingerprint, mir.fingerprint, "MIR"),
        )
        for actual, wanted, label in expected_fields:
            if actual != wanted:
                raise SurvivalEventBindingError(f"survival event binding {label} mismatch")
        if self.epoch != request.epoch:
            raise SurvivalEventBindingError("survival event binding epoch mismatch")
        if self.digest != expected:
            raise SurvivalEventBindingError("survival event binding seal mismatch")


def _binding_digest(**values: object) -> str:
    rows = tuple(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.sha256(_CTX + b"binding\x00" + "\n".join(rows).encode("utf-8")).hexdigest()


def bind_survival_decision_to_event(
    *,
    decision: SurvivalBranchDecision,
    branch: SurvivalBranch,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    matrix: MatrixIdentity,
    hara: HaraIdentity,
    matrix_admission: MatrixAdmission,
    request: CanonicalEffectRequest,
    sathra: Sathra,
    sathra_binding: SathraRequestBinding,
) -> SurvivalEventBinding:
    action = survival_action_commitment(
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        request=request,
    )
    result = SurvivalEventBinding(
        decision_digest=decision.digest,
        branch_digest=branch.branch_digest,
        action_commitment_digest=action,
        request_digest=request.digest,
        sathra_digest=sathra.digest,
        sathra_binding_digest=sathra_binding.digest,
        aevra_digest=aevra.digest,
        veyra_digest=veyra.digest,
        matrix_digest=matrix.digest,
        hara_digest=hara.digest,
        native_mir_fingerprint=mir.fingerprint,
        epoch=request.epoch,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _binding_digest(
            decision_digest=result.decision_digest,
            branch_digest=result.branch_digest,
            action_commitment_digest=result.action_commitment_digest,
            request_digest=result.request_digest,
            sathra_digest=result.sathra_digest,
            sathra_binding_digest=result.sathra_binding_digest,
            aevra_digest=result.aevra_digest,
            veyra_digest=result.veyra_digest,
            matrix_digest=result.matrix_digest,
            hara_digest=result.hara_digest,
            native_mir_fingerprint=result.native_mir_fingerprint,
            epoch=result.epoch,
        ),
    )
    result.assert_sealed(
        decision=decision,
        branch=branch,
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        matrix_admission=matrix_admission,
        request=request,
        sathra=sathra,
        sathra_binding=sathra_binding,
    )
    return result
