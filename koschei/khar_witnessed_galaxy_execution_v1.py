"""Galaxy execution wrapper that requires witnessed Khar implementation evidence.

The base Galaxy gate proves language/runtime constitutional relations.  This
wrapper adds a stronger precondition: independent external witnesses must agree
on the exact implementation measurement for this Veyra, native MIR and epoch.
Only then is the ordinary constitutional gate allowed to run.

The verified implementation root is evidence only.  It grants no authority and
cannot replace Khar, Sathra, Matrix/Hara, Morth, failure-root independence or
one-shot finality.
"""
from __future__ import annotations

from typing import Callable, TypeVar

from .galaxy_execution_gate_v1 import enforce_galaxy_critical_effect
from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_failure_independence_v1 import FailureIndependentSathra
from .khar_implementation_root_v1 import VerifiedKharImplementationRootV1
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
from .sathra_request_binding_v1 import SathraRequestBinding

_T = TypeVar("_T")


class KharWitnessedGalaxyExecutionError(ValueError):
    pass


def enforce_witnessed_galaxy_critical_effect(
    *,
    implementation_root: VerifiedKharImplementationRootV1,
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
    """Execute only when the external implementation root matches this reality."""

    try:
        if not isinstance(implementation_root, VerifiedKharImplementationRootV1):
            raise KharWitnessedGalaxyExecutionError("invalid witnessed implementation root")
        implementation_root.assert_for(
            veyra_digest=veyra.digest,
            native_mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
        )
    except KharWitnessedGalaxyExecutionError:
        raise
    except ValueError as error:
        raise KharWitnessedGalaxyExecutionError(str(error)) from error

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
