"""Bind six-axis Khar Sathra concurrence to exact privileged requests v1.

A critical effect must not accept a reusable or context-free Sathra. This layer
binds one sealed Sathra to one compiler-produced Aevra, one customer Veyra, one
canonical effect request, one epoch and the exact native MIR reality.

The existing native proof/request gate remains responsible for Library proof and
request replay protection. This layer adds the Galaxy constitutional requirement
that critical execution also possesses a valid 6/6 Sathra for that same event.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, TypeVar

from .galaxy_identity_v1 import AevraIdentity, VeyraIdentity
from .khar_sathra_v1 import Sathra
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import (
    CanonicalEffectRequest,
    RequestBoundProof,
    enforce_bound_effect,
)
from .native_sigil_enforcement_gate_v1 import EnforcementDecision

_CTX = b"koschei.sathra-request-binding/v1\x00"
_T = TypeVar("_T")


class SathraRequestBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SathraRequestBinding:
    request_digest: str
    sathra_digest: str
    aevra_digest: str
    veyra_digest: str
    native_mir_fingerprint: str
    epoch: int
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        mir: NativeSigilMir,
        veyra: VeyraIdentity,
        aevra: AevraIdentity,
        request: CanonicalEffectRequest,
        sathra: Sathra,
    ) -> None:
        # Normalize failures from the lower identity/MIR/request/Sathra layers so
        # callers cannot accidentally treat a malformed constituent as a valid
        # Galaxy-level binding merely because it raised a different exception.
        try:
            mir.assert_sealed()
            veyra.assert_sealed()
            aevra.assert_sealed(veyra, mir)
            request.assert_sealed(mir)
            sathra.assert_sealed()
        except ValueError as error:
            raise SathraRequestBindingError(str(error)) from error

        if sathra.aevra_digest != aevra.digest:
            raise SathraRequestBindingError("Sathra belongs to a different Aevra")
        if sathra.veyra_digest != veyra.digest:
            raise SathraRequestBindingError("Sathra belongs to a different Veyra")
        if sathra.event_digest != request.digest:
            raise SathraRequestBindingError("Sathra belongs to a different critical event")
        if sathra.reality_digest != mir.fingerprint:
            raise SathraRequestBindingError("Sathra belongs to a different executable reality")
        if sathra.epoch != request.epoch:
            raise SathraRequestBindingError("Sathra belongs to a different epoch")

        expected = _binding_digest(
            request_digest=request.digest,
            sathra_digest=sathra.digest,
            aevra_digest=aevra.digest,
            veyra_digest=veyra.digest,
            mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
        )
        if self.request_digest != request.digest:
            raise SathraRequestBindingError("Sathra request binding request mismatch")
        if self.sathra_digest != sathra.digest:
            raise SathraRequestBindingError("Sathra request binding concurrence mismatch")
        if self.aevra_digest != aevra.digest:
            raise SathraRequestBindingError("Sathra request binding Aevra mismatch")
        if self.veyra_digest != veyra.digest:
            raise SathraRequestBindingError("Sathra request binding Veyra mismatch")
        if self.native_mir_fingerprint != mir.fingerprint:
            raise SathraRequestBindingError("Sathra request binding reality mismatch")
        if self.epoch != request.epoch:
            raise SathraRequestBindingError("Sathra request binding epoch mismatch")
        if self.digest != expected:
            raise SathraRequestBindingError("Sathra request binding seal mismatch")


def _binding_digest(
    *,
    request_digest: str,
    sathra_digest: str,
    aevra_digest: str,
    veyra_digest: str,
    mir_fingerprint: str,
    epoch: int,
) -> str:
    rows = (
        f"request={request_digest}",
        f"sathra={sathra_digest}",
        f"aevra={aevra_digest}",
        f"veyra={veyra_digest}",
        f"reality={mir_fingerprint}",
        f"epoch={epoch}",
    )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


def bind_sathra_to_request(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    request: CanonicalEffectRequest,
    sathra: Sathra,
) -> SathraRequestBinding:
    result = SathraRequestBinding(
        request_digest=request.digest,
        sathra_digest=sathra.digest,
        aevra_digest=aevra.digest,
        veyra_digest=veyra.digest,
        native_mir_fingerprint=mir.fingerprint,
        epoch=request.epoch,
        digest=_binding_digest(
            request_digest=request.digest,
            sathra_digest=sathra.digest,
            aevra_digest=aevra.digest,
            veyra_digest=veyra.digest,
            mir_fingerprint=mir.fingerprint,
            epoch=request.epoch,
        ),
    )
    result.assert_sealed(mir, veyra, aevra, request, sathra)
    return result


def enforce_sathra_bound_effect(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    aevra: AevraIdentity,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    request_bound_proof: RequestBoundProof,
    sathra: Sathra,
    sathra_binding: SathraRequestBinding,
    effect: Callable[[CanonicalEffectRequest], _T],
) -> tuple[EnforcementDecision, _T | None]:
    """Run a critical effect only after both proof binding and exact 6/6 Sathra."""

    sathra_binding.assert_sealed(mir, veyra, aevra, request, sathra)
    return enforce_bound_effect(
        mir,
        request,
        proof,
        request_bound_proof,
        effect,
    )
