"""Galaxy execution wrapper that freshly verifies Khar implementation witnesses.

The base Galaxy gate proves language/runtime constitutional relations.  This
wrapper adds a stronger precondition: independent external witnesses must agree
on the exact implementation measurement for this Veyra, native MIR and epoch.
Only then is the ordinary constitutional gate allowed to run.

A ``VerifiedKharImplementationRootV1`` is a non-authoritative verification
report, not a credential.  This privileged boundary never accepts such a report
by itself: it re-verifies the original measurement and witness MACs against
external witness key material on every entry.  Directly constructing a report
therefore cannot bypass witness verification.

The external keys remain a deployment trust boundary.  Koschei software cannot
prove that caller-supplied bytes came from TPM/TEE/HSM/isolated verifier storage;
concrete deployments must source those keys independently from program state.
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
    verify_khar_implementation_root,
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
from .sathra_request_binding_v1 import SathraRequestBinding

_T = TypeVar("_T")


class KharWitnessedGalaxyExecutionError(ValueError):
    pass


def enforce_witnessed_galaxy_critical_effect(
    *,
    implementation_measurement: KharImplementationMeasurementV1,
    implementation_witnesses: tuple[KharImplementationWitnessV1, ...],
    implementation_witness_keys: Mapping[str, bytes],
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
    """Reverify implementation witnesses, then execute the exact Galaxy event."""

    try:
        root = verify_khar_implementation_root(
            implementation_measurement,
            implementation_witnesses,
            witness_keys=implementation_witness_keys,
        )
        root.assert_for(
            veyra_digest=veyra.digest,
            native_mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
        )
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
