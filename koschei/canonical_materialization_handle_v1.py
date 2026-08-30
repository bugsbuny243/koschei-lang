"""Opaque canonical materialization and constitutional effect execution v1.

Sanctioned reconstruction never returns `NativeSigilMir` to the broad runtime. Hidden MIR
stays in a trusted registry and the caller receives an opaque one-shot handle bound to the
exact canonical request and the reconstruction Veyra through keyed material.

For privileged `CanonicalEffectRequest` execution, the sanctioned materialization gate
requires one exact-request, deny-only capability power-domain constraint before touching
canonical materialization state. It then delegates to the existing
`enforce_galaxy_critical_effect` constitutional path. Khar, living Aevra, current
Matrix/Hara, 6/6 Sathra, failure-root independence, exact request proof and durable atomic
finality therefore remain the authoritative critical-effect physics rather than being
reimplemented here.

This Python bootstrap does not provide process isolation. Native runtime compartments must
keep registry internals and raw canonical state inaccessible to observer/runtime surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import Lock
from typing import Callable, TypeVar

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .galaxy_execution_gate_v1 import enforce_galaxy_critical_effect
from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_failure_independence_v1 import FailureIndependentSathra
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
from .representation_boundary_v1 import seal_canonical_semantics_v1
from .request_capability_domain_constraint_v1 import RequestCapabilityDomainConstraintV1
from .sathra_request_binding_v1 import SathraRequestBinding

_CTX = b"koschei.canonical-materialization-handle/v1\x00"
_REQUEST_CTX = b"koschei.canonical-materialization-request-binding/v1\x00"
_T = TypeVar("_T")


class CanonicalMaterializationHandleV1Error(ValueError):
    pass


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise CanonicalMaterializationHandleV1Error(
            "materialization key must contain at least 32 bytes"
        )
    return value


def _epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CanonicalMaterializationHandleV1Error(
            "materialization epoch must be a non-negative integer"
        )
    return value


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalMaterializationHandleV1Error(f"{label} cannot be empty")
    return value.strip()


def _request_binding(
    key: bytes,
    canonical_request_digest: str,
    veyra_digest: str,
) -> str:
    request_digest = _text(canonical_request_digest, "canonical_request_digest")
    living_veyra = _text(veyra_digest, "veyra_digest")
    payload = b"\n".join(
        (
            request_digest.encode("ascii"),
            living_veyra.encode("ascii"),
        )
    )
    return hmac.new(key, _REQUEST_CTX + payload, hashlib.sha256).hexdigest()


def _handle_payload(
    *,
    handle_id: str,
    purpose: str,
    request_binding_digest: str,
    issued_epoch: int,
    expires_before_epoch: int,
    reconstruction_receipt_digest: str,
) -> bytes:
    rows = (
        f"handle={handle_id}",
        f"purpose={purpose}",
        f"request-binding={request_binding_digest}",
        f"issued-epoch={issued_epoch}",
        f"expires-before={expires_before_epoch}",
        f"reconstruction-receipt={reconstruction_receipt_digest}",
        "opaque=1",
        "single-use=1",
        "version=1",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CanonicalMaterializationHandleV1:
    """Runtime-safe reference to one hidden canonical world/request pair.

    The handle contains neither raw request identity nor Veyra identity. Its keyed request
    binding is nevertheless scoped to both, so a handle cannot be moved to another living
    Galaxy without failing trusted-registry verification.
    """

    handle_id: str
    purpose: str
    request_binding_digest: str
    issued_epoch: int
    expires_before_epoch: int
    reconstruction_receipt_digest: str
    handle_digest: str
    opaque: bool = True
    single_use: bool = True
    version: int = 1

    def assert_authenticated(self, *, materialization_key: bytes) -> None:
        key = _key(materialization_key)
        if self.version != 1 or self.opaque is not True or self.single_use is not True:
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization handle flags are invalid"
            )
        issued = _epoch(self.issued_epoch)
        expires = _epoch(self.expires_before_epoch)
        if expires <= issued:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle expiry must be after issue epoch"
            )
        expected = hmac.new(
            key,
            _handle_payload(
                handle_id=_text(self.handle_id, "handle_id"),
                purpose=_text(self.purpose, "purpose"),
                request_binding_digest=_text(
                    self.request_binding_digest, "request_binding_digest"
                ),
                issued_epoch=issued,
                expires_before_epoch=expires,
                reconstruction_receipt_digest=_text(
                    self.reconstruction_receipt_digest,
                    "reconstruction_receipt_digest",
                ),
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(self.handle_digest, expected):
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization handle authentication failed"
            )


@dataclass(slots=True)
class _MaterializationEntryV1:
    hidden_mir: NativeSigilMir
    canonical_seal_digest: str
    veyra_digest: str
    purpose: str
    canonical_request_digest: str
    request_binding_digest: str
    issued_epoch: int
    expires_before_epoch: int
    reconstruction_receipt_digest: str


class CanonicalMaterializationRegistryV1:
    """Trusted process-local custody for hidden canonical MIR and Veyra binding."""

    def __init__(self, *, materialization_key: bytes) -> None:
        self._key = _key(materialization_key)
        self._lock = Lock()
        self._entries: dict[str, _MaterializationEntryV1] = {}

    def mint(
        self,
        *,
        hidden_mir: NativeSigilMir,
        veyra: VeyraIdentity,
        canonical_seal_digest: str,
        canonical_request: CanonicalEffectRequest,
        purpose: str,
        issued_epoch: int,
        expires_before_epoch: int,
        reconstruction_receipt_digest: str,
    ) -> CanonicalMaterializationHandleV1:
        hidden_mir.assert_sealed()
        veyra.assert_sealed()
        canonical_request.assert_sealed(hidden_mir)
        seal = seal_canonical_semantics_v1(hidden_mir)
        if seal.seal_digest != canonical_seal_digest:
            raise CanonicalMaterializationHandleV1Error(
                "materialization canonical seal differs from hidden MIR"
            )
        purpose_value = _text(purpose, "purpose")
        issued = _epoch(issued_epoch)
        expires = _epoch(expires_before_epoch)
        if expires <= issued:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle expiry must be after issue epoch"
            )
        if canonical_request.epoch != issued:
            raise CanonicalMaterializationHandleV1Error(
                "canonical request epoch differs from materialization issue epoch"
            )
        receipt_digest = _text(
            reconstruction_receipt_digest, "reconstruction_receipt_digest"
        )
        request_binding = _request_binding(
            self._key,
            canonical_request.digest,
            veyra.digest,
        )
        with self._lock:
            while True:
                handle_id = secrets.token_hex(32)
                if handle_id not in self._entries:
                    break
            handle = CanonicalMaterializationHandleV1(
                handle_id=handle_id,
                purpose=purpose_value,
                request_binding_digest=request_binding,
                issued_epoch=issued,
                expires_before_epoch=expires,
                reconstruction_receipt_digest=receipt_digest,
                handle_digest="",
            )
            object.__setattr__(
                handle,
                "handle_digest",
                hmac.new(
                    self._key,
                    _handle_payload(
                        handle_id=handle.handle_id,
                        purpose=handle.purpose,
                        request_binding_digest=handle.request_binding_digest,
                        issued_epoch=handle.issued_epoch,
                        expires_before_epoch=handle.expires_before_epoch,
                        reconstruction_receipt_digest=handle.reconstruction_receipt_digest,
                    ),
                    hashlib.sha256,
                ).hexdigest(),
            )
            self._entries[handle_id] = _MaterializationEntryV1(
                hidden_mir=hidden_mir,
                canonical_seal_digest=seal.seal_digest,
                veyra_digest=veyra.digest,
                purpose=purpose_value,
                canonical_request_digest=canonical_request.digest,
                request_binding_digest=request_binding,
                issued_epoch=issued,
                expires_before_epoch=expires,
                reconstruction_receipt_digest=receipt_digest,
            )
        handle.assert_authenticated(materialization_key=self._key)
        return handle

    def _consume_hidden_mir(
        self,
        handle: CanonicalMaterializationHandleV1,
        *,
        purpose: str,
        canonical_request: CanonicalEffectRequest,
        veyra: VeyraIdentity,
        current_epoch: int,
    ) -> NativeSigilMir:
        """Trusted-only one-shot resolution used by the constitutional effect gate."""

        if not isinstance(handle, CanonicalMaterializationHandleV1):
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization handle v1 required"
            )
        veyra.assert_sealed()
        handle.assert_authenticated(materialization_key=self._key)
        requested_purpose = _text(purpose, "purpose")
        current = _epoch(current_epoch)
        if requested_purpose != handle.purpose:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle purpose mismatch"
            )
        expected_request_binding = _request_binding(
            self._key,
            canonical_request.digest,
            veyra.digest,
        )
        if not hmac.compare_digest(
            expected_request_binding, handle.request_binding_digest
        ):
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle canonical request/Veyra mismatch"
            )
        if canonical_request.epoch != current:
            raise CanonicalMaterializationHandleV1Error(
                "canonical request epoch differs from current materialization epoch"
            )
        if current < handle.issued_epoch:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle is not live yet"
            )
        if current >= handle.expires_before_epoch:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle expired"
            )
        with self._lock:
            entry = self._entries.get(handle.handle_id)
            if entry is None:
                raise CanonicalMaterializationHandleV1Error(
                    "canonical materialization handle already consumed or unknown"
                )
            if (
                entry.veyra_digest != veyra.digest
                or entry.purpose != handle.purpose
                or entry.request_binding_digest != handle.request_binding_digest
                or entry.canonical_request_digest != canonical_request.digest
                or entry.issued_epoch != handle.issued_epoch
                or entry.expires_before_epoch != handle.expires_before_epoch
                or entry.reconstruction_receipt_digest
                != handle.reconstruction_receipt_digest
            ):
                raise CanonicalMaterializationHandleV1Error(
                    "canonical materialization registry binding mismatch"
                )
            hidden = entry.hidden_mir
            seal = seal_canonical_semantics_v1(hidden)
            if seal.seal_digest != entry.canonical_seal_digest:
                raise CanonicalMaterializationHandleV1Error(
                    "canonical materialization registry MIR seal mismatch"
                )
            canonical_request.assert_sealed(hidden)
            # Crossing the trusted materialization boundary is one-shot. Once the exact
            # request + living Veyra + current epoch are accepted, later Khar/Galaxy denial
            # burns this handle rather than leaving a reusable canonical capability.
            del self._entries[handle.handle_id]
        hidden.assert_sealed()
        return hidden


@dataclass(frozen=True, slots=True)
class GalaxyMaterializationContextV1:
    """Non-authoritative bundle of existing Galaxy constitutional inputs.

    This creates no new constitutional semantics. `assert_shape` only prevents accidental
    API misuse; `enforce_galaxy_critical_effect` remains the authority for all Khar/Galaxy
    validation and durable finality.
    """

    black_hole: DurableBlackHole
    matrix_horizon: DurableMatrixHorizonFence
    coordinator: AtomicExecutionCoordinator
    veyra: VeyraIdentity
    aevra: AevraIdentity
    matrix: MatrixIdentity
    hara: HaraIdentity
    matrix_admission: MatrixAdmission
    sathra: Sathra
    sathra_binding: SathraRequestBinding
    failure_independence: FailureIndependentSathra
    authority: bool = False
    version: int = 1

    def assert_shape(self) -> None:
        if self.version != 1 or self.authority is not False:
            raise CanonicalMaterializationHandleV1Error(
                "Galaxy materialization context flags are invalid"
            )
        expected = (
            (self.black_hole, DurableBlackHole, "DurableBlackHole"),
            (self.matrix_horizon, DurableMatrixHorizonFence, "DurableMatrixHorizonFence"),
            (self.coordinator, AtomicExecutionCoordinator, "AtomicExecutionCoordinator"),
            (self.veyra, VeyraIdentity, "VeyraIdentity"),
            (self.aevra, AevraIdentity, "AevraIdentity"),
            (self.matrix, MatrixIdentity, "MatrixIdentity"),
            (self.hara, HaraIdentity, "HaraIdentity"),
            (self.matrix_admission, MatrixAdmission, "MatrixAdmission"),
            (self.sathra, Sathra, "Sathra"),
            (self.sathra_binding, SathraRequestBinding, "SathraRequestBinding"),
            (
                self.failure_independence,
                FailureIndependentSathra,
                "FailureIndependentSathra",
            ),
        )
        for value, kind, label in expected:
            if not isinstance(value, kind):
                raise CanonicalMaterializationHandleV1Error(
                    f"Galaxy materialization context requires {label}"
                )


@dataclass(frozen=True, slots=True)
class CanonicalMaterializationEffectGateV1:
    """One-shot bridge from opaque handle to the existing Galaxy critical-effect gate."""

    registry: CanonicalMaterializationRegistryV1
    handle: CanonicalMaterializationHandleV1
    request: CanonicalEffectRequest
    proof: NativeSigilProofBundle
    bound: RequestBoundProof
    domain_constraint: RequestCapabilityDomainConstraintV1
    continuity: ContinuityEpochAuthorityV1
    galaxy: GalaxyMaterializationContextV1
    purpose: str = "execute"

    def __post_init__(self) -> None:
        if not isinstance(self.registry, CanonicalMaterializationRegistryV1):
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization registry v1 required"
            )
        if not isinstance(self.handle, CanonicalMaterializationHandleV1):
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization handle v1 required"
            )
        if not isinstance(self.request, CanonicalEffectRequest):
            raise CanonicalMaterializationHandleV1Error(
                "canonical effect request required"
            )
        if not isinstance(self.bound, RequestBoundProof):
            raise CanonicalMaterializationHandleV1Error(
                "request-bound proof required"
            )
        if self.bound.request_digest != self.request.digest:
            raise CanonicalMaterializationHandleV1Error(
                "request-bound proof does not bind supplied canonical request"
            )
        if self.bound.proof_digest != self.proof.digest:
            raise CanonicalMaterializationHandleV1Error(
                "request-bound proof does not bind supplied native proof"
            )
        if not isinstance(
            self.domain_constraint,
            RequestCapabilityDomainConstraintV1,
        ):
            raise CanonicalMaterializationHandleV1Error(
                "request capability-domain constraint v1 required"
            )
        # This is deliberately checked before any one-shot materialization state
        # is touched. A malformed/foreign/cross-domain constraint cannot burn a
        # valid handle and cannot produce an ALLOW decision by itself.
        self.domain_constraint.assert_sealed(self.request)
        if not isinstance(self.continuity, ContinuityEpochAuthorityV1):
            raise CanonicalMaterializationHandleV1Error(
                "Continuity epoch authority v1 required"
            )
        self.continuity.assert_sealed()
        if not isinstance(self.galaxy, GalaxyMaterializationContextV1):
            raise CanonicalMaterializationHandleV1Error(
                "Galaxy materialization context v1 required"
            )
        self.galaxy.assert_shape()
        _text(self.purpose, "purpose")

    def execute(
        self,
        effect: Callable[[CanonicalEffectRequest], _T],
    ) -> tuple[EnforcementDecision, _T | None, AtomicClaim]:
        # Re-assert immediately before the privileged transition. The object is
        # frozen, but this also makes canonical contract drift fail closed.
        self.domain_constraint.assert_sealed(self.request)
        current = self.continuity.current_epoch()
        hidden_mir = self.registry._consume_hidden_mir(
            self.handle,
            purpose=self.purpose,
            canonical_request=self.request,
            veyra=self.galaxy.veyra,
            current_epoch=current,
        )
        return enforce_galaxy_critical_effect(
            black_hole=self.galaxy.black_hole,
            matrix_horizon=self.galaxy.matrix_horizon,
            coordinator=self.galaxy.coordinator,
            mir=hidden_mir,
            veyra=self.galaxy.veyra,
            aevra=self.galaxy.aevra,
            matrix=self.galaxy.matrix,
            hara=self.galaxy.hara,
            matrix_admission=self.galaxy.matrix_admission,
            request=self.request,
            proof=self.proof,
            request_bound_proof=self.bound,
            sathra=self.galaxy.sathra,
            sathra_binding=self.galaxy.sathra_binding,
            failure_independence=self.galaxy.failure_independence,
            effect=effect,
        )
