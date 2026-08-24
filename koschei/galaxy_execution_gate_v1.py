"""Koschei Galaxy constitutional critical-execution gate v1.

This is the base composed constitutional boundary for privileged Koschei events.
A critical effect is eligible only when:

1. its Veyra is bound to the exact canonical Khar v1 constitution;
2. its Aevra is still living outside the Black Hole;
3. it is admitted to the durable current Matrix/Hara execution reality;
4. its Sathra is six-axis complete and exact-event bound;
5. all six axes carry a sealed failure-root independence proof;
6. the compiler/Library proof is bound to the exact canonical request;
7. the request is atomically claimed and finalized exactly once.

This gate proves constitutional relations inside the Koschei software boundary.
Deployments that possess independent compiler/runtime measurement witnesses use
``khar_witnessed_galaxy_execution_v1`` above this gate; the base gate alone does
not claim physical implementation identity.

This module creates no authority and performs no counterattack. It composes the
existing constitutional laws into one fail-closed execution path so callers do
not need to assemble a weaker subset by accident.
"""
from __future__ import annotations

from typing import Callable, TypeVar

from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_constitution_v1 import require_canonical_khar_v1
from .khar_failure_independence_v1 import (
    FailureIndependentSathra,
    require_failure_independent_sathra,
)
from .khar_sathra_v1 import Sathra
from .matrix_horizon_fence_v1 import DurableMatrixHorizonFence
from .matrix_reality_v1 import HaraIdentity, MatrixAdmission, MatrixIdentity
from .morth_black_hole_v1 import DurableBlackHole
from .native_sigil_atomic_execution_coordinator_v1 import (
    AtomicClaim,
    AtomicExecutionCoordinator,
)
from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof
from .sathra_request_binding_v1 import (
    SathraRequestBinding,
    enforce_atomic_sathra_bound_effect,
)

_T = TypeVar("_T")


class GalaxyExecutionError(ValueError):
    pass


def enforce_galaxy_critical_effect(
    *,
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
    """Execute only through the complete base Galaxy constitutional path."""

    try:
        require_canonical_khar_v1(veyra)
        black_hole.require_living(aevra, veyra, mir)
        matrix_admission.assert_sealed(matrix, hara, veyra, aevra, mir)
        matrix_horizon.require_current(matrix_admission)
        if matrix_admission.epoch != request.epoch:
            raise GalaxyExecutionError(
                "Matrix/Hara admission belongs to a different request epoch"
            )
        require_failure_independent_sathra(sathra, failure_independence)
    except GalaxyExecutionError:
        raise
    except ValueError as error:
        raise GalaxyExecutionError(str(error)) from error

    return enforce_atomic_sathra_bound_effect(
        mir,
        veyra,
        aevra,
        request,
        proof,
        request_bound_proof,
        sathra,
        sathra_binding,
        coordinator,
        effect,
    )
