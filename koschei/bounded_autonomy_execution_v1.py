"""Execute a bounded-autonomy proposal only through Koschei survival physics v1.

Automation does not receive a privileged side door.  A proposal must revalidate
against the exact candidate set, objective and bounds, its chosen branch must be
the one bound to the exact survival event, and execution then proceeds through
the normal survival-mode Galaxy constitutional gate.
"""
from __future__ import annotations

from typing import Callable, TypeVar

from .bounded_autonomy_v1 import AutonomyBounds, BoundedAutonomyProposal
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
from .survival_branch_v1 import SurvivalBranch, SurvivalObjective
from .survival_event_binding_v1 import SurvivalEventBinding
from .survival_execution_gate_v1 import enforce_survival_branch_effect

_T = TypeVar("_T")


class BoundedAutonomyExecutionError(ValueError):
    pass


def enforce_bounded_autonomy_effect(
    *,
    proposal: BoundedAutonomyProposal,
    branches: tuple[SurvivalBranch, ...],
    objective: SurvivalObjective,
    bounds: AutonomyBounds,
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
    """Run no autonomous effect unless the entire constitutional chain agrees."""

    try:
        proposal.assert_sealed(branches=branches, objective=objective, bounds=bounds)
        if proposal.decision.chosen_branch_digest != branch.branch_digest:
            raise BoundedAutonomyExecutionError(
                "autonomy execution branch is not the proposal's chosen branch"
            )
    except BoundedAutonomyExecutionError:
        raise
    except ValueError as error:
        raise BoundedAutonomyExecutionError(str(error)) from error

    return enforce_survival_branch_effect(
        decision=proposal.decision,
        branch=branch,
        survival_binding=survival_binding,
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
