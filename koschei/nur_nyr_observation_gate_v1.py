"""Fail-closed observation boundary for live Nyr v2 surfaces.

This is the sanctioned Lang-side observer path for Nyr v2. It shares one typed
`ContinuityEpochAuthorityV1` contract with reconstruction and materialization. The gate
therefore does not accept an independent caller-supplied epoch callback.

Visible data is rendered only after hidden-input projection integrity and current
Continuity liveness succeed. Python cannot make lower-level render/project helpers
physically inaccessible; native/runtime surfaces must preserve the same boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir
from .nur_nyr_projection_v2 import (
    NyrSurfaceV2,
    project_native_mir_nyr_v2,
    require_live_nyr_surface_v2,
)


class NyrObservationGateV1Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NyrObservationGateV1:
    """Trusted live-observation boundary for one canonical Nyr projection context."""

    mir: NativeSigilMir
    veyra: VeyraIdentity
    envelope: AdaptiveVisibilityEnvelopeV0
    veil_key: bytes
    continuity: ContinuityEpochAuthorityV1

    def __post_init__(self) -> None:
        self.mir.assert_sealed()
        self.veyra.assert_sealed()
        if not isinstance(self.envelope, AdaptiveVisibilityEnvelopeV0):
            raise NyrObservationGateV1Error("adaptive visibility envelope required")
        if self.envelope.authority:
            raise NyrObservationGateV1Error(
                "observation gate requires authority-free envelope"
            )
        if not self.envelope.allowed:
            raise NyrObservationGateV1Error(
                "contained Nur envelope cannot open observation gate"
            )
        if not isinstance(self.veil_key, bytes) or len(self.veil_key) < 32:
            raise NyrObservationGateV1Error(
                "observation gate veil key must contain at least 32 bytes"
            )
        if not isinstance(self.continuity, ContinuityEpochAuthorityV1):
            raise NyrObservationGateV1Error(
                "Continuity epoch authority v1 required"
            )
        self.continuity.assert_sealed()

    def render(self, surface: NyrSurfaceV2) -> str:
        """Render observer-visible data only after live projection verification."""

        current = self.continuity.current_epoch()
        require_live_nyr_surface_v2(
            surface,
            self.mir,
            self.veyra,
            self.envelope,
            veil_key=self.veil_key,
            current_visibility_epoch=current,
        )
        return surface.render()

    def project_and_render(self) -> str:
        """Project and render only when this envelope belongs to current Continuity."""

        current = self.continuity.current_epoch()
        if self.envelope.visibility_epoch != current:
            raise NyrObservationGateV1Error(
                "Nur visibility envelope is not current under Continuity"
            )
        surface = project_native_mir_nyr_v2(
            self.mir,
            self.veyra,
            self.envelope,
            veil_key=self.veil_key,
        )
        require_live_nyr_surface_v2(
            surface,
            self.mir,
            self.veyra,
            self.envelope,
            veil_key=self.veil_key,
            current_visibility_epoch=current,
        )
        return surface.render()
