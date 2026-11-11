"""Koschei survival-mode critical execution gate v1.

A survival plan is not authority: it must be bound to the exact event and then
the normal living/current-Hara/6-axis/failure-independent/one-shot
constitutional gate must still succeed.

Two entry points are explicit:

- ``enforce_survival_branch_effect`` composes the base constitutional Galaxy
  path and remains useful where no external implementation witness exists;
- ``enforce_witnessed_survival_branch_effect`` is the stronger deployment path.
  It forwards the original implementation measurement, witnesses and external
  witness key material so the witnessed Galaxy boundary can freshly verify them.

Automation and recovery code must not silently treat a cached verification
report as proof of physical compiler/runtime identity.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, TypeVar

from .galaxy_execution_gate_v1 import enforce_galaxy_critical_effect
from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_failure_independence_v1 import FailureIndependentSathra
from .khar_implementation_root_v1 import (
    KharImplementationMeasurementV1,
    KharImplementationWitnessV1,
)
from .khar_sathra_v1 import Sathra
from .khar_witnessed_galaxy_execution_v1 import enforce_witnessed_galaxy_critical_effect
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


def _require_exact_survival_binding(
    *,
    decision: SurvivalBranchDecision,
    branch: SurvivalBranch,
    survival_binding: SurvivalEventBinding,
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
    """Execute a chosen survival branch through the base constitutional path."""

    _require_exact_survival_binding(
        decision=decision,
        branch=branch,
        survival_binding=survival_binding,
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


def enforce_witnessed_survival_branch_effect(
    *,
    implementation_measurement: KharImplementationMeasurementV1,
    implementation_witnesses: tuple[KharImplementationWitnessV1, ...],
    implementation_witness_keys: Mapping[str, bytes],
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
    """Execute survival mode only after exact-event and fresh witness verification."""

    _require_exact_survival_binding(
        decision=decision,
        branch=branch,
        survival_binding=survival_binding,
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
    return enforce_witnessed_galaxy_critical_effect(
        implementation_measurement=implementation_measurement,
        implementation_witnesses=implementation_witnesses,
        implementation_witness_keys=implementation_witness_keys,
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
