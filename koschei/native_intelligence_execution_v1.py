"""Koschei-native intelligence execution composition v1.

The trained Qwen model lives inside Koschei Lang as an authority-free
intelligence plane.  A model observation/output is useful only when it is bound
to the exact bounded-autonomy proposal for the exact Veyra, native MIR and
request epoch.  Execution then still passes the witnessed bounded-autonomy,
survival and Galaxy constitutional gates.

There is deliberately no model-only execution function in this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, TypeVar

from .bounded_autonomy_execution_v1 import enforce_witnessed_bounded_autonomy_effect
from .bounded_autonomy_v1 import AutonomyBounds, BoundedAutonomyProposal
from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_failure_independence_v1 import FailureIndependentSathra
from .khar_implementation_root_v1 import (
    KharImplementationMeasurementV1,
    KharImplementationWitnessV1,
)
from .khar_sathra_v1 import Sathra
from .matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from .matrix_reality_v1 import HaraIdentity, MatrixAdmission, MatrixIdentity
from .morth_black_hole_v1 import DurableBlackHole
from .native_intelligence_v1 import (
    NativeIntelligenceEventBindingV1,
    NativeIntelligenceIdentityV1,
)
from .native_sigil_atomic_execution_coordinator_v1 import AtomicClaim, AtomicExecutionCoordinator
from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof
from .sathra_request_binding_v1 import SathraRequestBinding
from .survival_branch_v1 import SurvivalBranch, SurvivalObjective
from .survival_event_binding_v1 import SurvivalEventBinding

_T = TypeVar("_T")


class NativeIntelligenceExecutionError(ValueError):
    pass


def enforce_native_intelligence_effect(
    *,
    intelligence: NativeIntelligenceIdentityV1,
    intelligence_binding: NativeIntelligenceEventBindingV1,
    implementation_measurement: KharImplementationMeasurementV1,
    implementation_witnesses: tuple[KharImplementationWitnessV1, ...],
    implementation_witness_keys: Mapping[str, bytes],
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
    """Execute no model-originated action outside the full witnessed Koschei path."""

    try:
        intelligence.assert_sealed()
        proposal.assert_sealed(branches=branches, objective=objective, bounds=bounds)
        intelligence_binding.assert_for(
            intelligence,
            veyra_digest=veyra.digest,
            native_mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
            proposal_digest=proposal.digest,
        )
    except ValueError as error:
        raise NativeIntelligenceExecutionError(str(error)) from error

    return enforce_witnessed_bounded_autonomy_effect(
        implementation_measurement=implementation_measurement,
        implementation_witnesses=implementation_witnesses,
        implementation_witness_keys=implementation_witness_keys,
        proposal=proposal,
        branches=branches,
        objective=objective,
        bounds=bounds,
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
