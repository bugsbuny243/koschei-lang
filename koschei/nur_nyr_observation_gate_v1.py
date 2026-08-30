"""Fail-closed observation boundary for live Nyr v2 surfaces.

This module is the sanctioned Lang-side observation path for Nyr v2. The gate
keeps hidden canonical inputs and the veil key on the trusted side of the
boundary and asks a trusted epoch source for liveness at the instant a surface
is consumed. Visible Nyr data is rendered only after integrity and epoch
verification succeed.

The Python bootstrap cannot make direct imports of lower-level helpers
physically impossible. Production backends must preserve this boundary in the
native runtime/API surface instead of exporting raw render primitives as an
authoritative observation path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir
from .nur_nyr_projection_v2 import NyrSurfaceV2, require_live_nyr_surface_v2


class NyrObservationGateV1Error(ValueError):
    pass


EpochSource = Callable[[], int]


@dataclass(frozen=True, slots=True)
class NyrObservationGateV1:
    """Trusted live-observation boundary for one canonical Nyr projection context."""

    mir: NativeSigilMir
    veyra: VeyraIdentity
    envelope: AdaptiveVisibilityEnvelopeV0
    veil_key: bytes
    epoch_source: EpochSource

    def __post_init__(self) -> None:
        self.mir.assert_sealed()
        self.veyra.assert_sealed()
        if not isinstance(self.envelope, AdaptiveVisibilityEnvelopeV0):
            raise NyrObservationGateV1Error("adaptive visibility envelope required")
        if self.envelope.authority:
            raise NyrObservationGateV1Error("observation gate requires authority-free envelope")
        if not self.envelope.allowed:
            raise NyrObservationGateV1Error("contained Nur envelope cannot open observation gate")
        if not isinstance(self.veil_key, bytes) or len(self.veil_key) < 32:
            raise NyrObservationGateV1Error("observation gate veil key must contain at least 32 bytes")
        if not callable(self.epoch_source):
            raise NyrObservationGateV1Error("trusted epoch source must be callable")

    def render(self, surface: NyrSurfaceV2) -> str:
        """Render observer-visible data only after live projection verification."""

        try:
            current_epoch = self.epoch_source()
        except Exception as exc:  # trusted boundary failure is always deny
            raise NyrObservationGateV1Error("trusted epoch source failed closed") from exc
        if not isinstance(current_epoch, int) or isinstance(current_epoch, bool) or current_epoch < 0:
            raise NyrObservationGateV1Error("trusted epoch source returned an invalid epoch")

        require_live_nyr_surface_v2(
            surface,
            self.mir,
            self.veyra,
            self.envelope,
            veil_key=self.veil_key,
            current_visibility_epoch=current_epoch,
        )
        return surface.render()
