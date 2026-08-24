"""Koschei survival-mode critical execution gate v1.

This gate composes a sealed survival-branch decision with the strongest current
Galaxy critical-execution path.  The survival plan is not authority: it must be
bound to the exact event and then the normal living/current-Hara/6-axis/
failure-independent/one-shot constitutional gate must still succeed.
"""
from __future__ import annotations

from typing import Callable, TypeVar

from .galaxy_execution_gate_v1 import enforce_galaxy_critical_effect
from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_failure_independence_v1 import FailureIndependentSathra
from .khar_sathra_v1 import Sathra
from .matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from .matrix_reality_v1 import HaraIdentity, MatrixAdmission, MatrixIdentity
from .morth_black_hole_v1 import DurableBlackHole
from .native_sigil_atomic_execution_coordinator_v1 import AtomicClaim, AtomicExecutionCoordinator
from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof
from .sathra_request_binding_v1 import SathraRequestBinding
from .survival_branch_v1 import SurvivalBranch, SurvivalBranchDecision
from .survival_event_binding_v1 import SurvivalEventBinding

_T = TypeVar("_T")


class SurvivalExecutionError(ValueError):
    pass


def enforce_survival_branch_effect(
    *,
    decision: SurvivalBranchDecision,
    branch: SurvivalBranch,
    survival_binding: SurvivalEventBinding,
    black_hole: DurableBlackHole,
    matrix_horizon: DurableMatrixHorizonFence,
    coordinator: AtomicExecutionCoordinator,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    matrix: MatrixIdentity,
    hara: HaraIdentity,
    matrix_admission: MatrixAdmission,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    request_bound_proof: RequestBoundProof,
    sathra: Sathra,
    sathra_binding: SathraRequestBinding,
    failure_independence: FailureIndependentSathra,
    effect: Callable[[CanonicalEffectRequest], _T],
) -> tuple[EnforcementDecision, _T | None, AtomicClaim]:
    """Execute a chosen survival branch only as its exact constitutional event."""

    try:
        survival_binding.assert_sealed(
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
    except ValueError as error:
        raise SurvivalExecutionError(str(error)) from error

    return enforce_galaxy_critical_effect(
        black_hole=black_hole,
        matrix_horizon=matrix_horizon,
        coordinator=coordinator,
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        matrix_admission=matrix_admission,
        request=request,
        proof=proof,
        request_bound_proof=request_bound_proof,
        sathra=sathra,
        sathra_binding=sathra_binding,
        failure_independence=failure_independence,
        effect=effect,
    )
