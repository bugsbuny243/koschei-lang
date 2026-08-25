"""Canonical semantic / observable representation boundary v1.

This module turns the Koschei rule ``observable world != canonical world`` into
an executable contract around native sigil MIR and Nur/Nyr v2.

The observable object never contains canonical sigil names, canonical subjects,
semantic-domain labels, authority flags, source locations, MIR fingerprints, or
Veyra identity. A trusted runtime can re-materialize canonical semantics only
from hidden sealed MIR plus an exact, time-scoped reconstruction grant.

This is representation separation, not a claim of cryptographic invisibility.
Side channels, a compromised trusted runtime, leaked reconstruction keys, or a
host that can inspect canonical state remain outside the protection of this
slice.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir
from .nur_nyr_projection_v2 import NyrSurfaceV2, project_native_mir_nyr_v2

_CTX = b"koschei.representation-boundary/v1\x00"


class RepresentationBoundaryV1Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalSemanticSealV1:
    """Trusted-side identity for one sealed canonical semantic world."""

    mir_fingerprint: str
    universe_plan_digest: str
    binding_count: int
    seal_digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.binding_count <= 0:
            raise RepresentationBoundaryV1Error(
                "canonical semantic seal requires at least one binding"
            )
        expected = _canonical_seal_digest(
            self.mir_fingerprint,
            self.universe_plan_digest,
            self.binding_count,
        )
        if not hmac.compare_digest(self.seal_digest, expected):
            raise RepresentationBoundaryV1Error("canonical semantic seal mismatch")


@dataclass(frozen=True, slots=True)
class ObservableRepresentationV1:
    """Observer-facing representation with no canonical identifiers."""

    surface: NyrSurfaceV2
    visibility_epoch: int
    expires_before_epoch: int
    representation_digest: str
    version: int = 1

    def assert_live(self, *, current_epoch: int) -> None:
        if current_epoch < 0:
            raise RepresentationBoundaryV1Error("current epoch must be non-negative")
        if self.visibility_epoch != self.surface.visibility_epoch:
            raise RepresentationBoundaryV1Error(
                "representation/surface epoch mismatch"
            )
        if self.expires_before_epoch != self.surface.expires_before_epoch:
            raise RepresentationBoundaryV1Error(
                "representation/surface expiry mismatch"
            )
        if current_epoch < self.visibility_epoch:
            raise RepresentationBoundaryV1Error("representation epoch is not active yet")
        if current_epoch >= self.expires_before_epoch:
            raise RepresentationBoundaryV1Error("observable representation expired")


@dataclass(frozen=True, slots=True)
class ReconstructionGrantV1:
    """A narrow capability to re-materialize hidden canonical semantics."""

    grant_id: str
    purpose: str
    visibility_epoch: int
    expires_before_epoch: int
    context_digest: str
    authorization_mac: str
    version: int = 1


def _hex64(value: str, *, field: str) -> str:
    if len(value) != 64:
        raise RepresentationBoundaryV1Error(f"{field} must be a sha256 hex digest")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise RepresentationBoundaryV1Error(
            f"{field} must be hexadecimal"
        ) from exc
    return value


def _require_key(value: bytes, *, field: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise RepresentationBoundaryV1Error(
            f"{field} must contain at least 32 bytes"
        )
    return value


def _canonical_seal_digest(
    mir_fingerprint: str,
    universe_plan_digest: str,
    binding_count: int,
) -> str:
    _hex64(mir_fingerprint, field="MIR fingerprint")
    _hex64(universe_plan_digest, field="universe plan digest")
    if binding_count <= 0:
        raise RepresentationBoundaryV1Error(
            "canonical semantic seal requires at least one binding"
        )
    payload = "\n".join(
        (
            f"mir={mir_fingerprint}",
            f"universe={universe_plan_digest}",
            f"bindings={binding_count}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"canonical-seal\x00" + payload).hexdigest()


def seal_canonical_semantics_v1(mir: NativeSigilMir) -> CanonicalSemanticSealV1:
    if not isinstance(mir, NativeSigilMir):
        raise RepresentationBoundaryV1Error(
            "canonical semantic sealing requires NativeSigilMir"
        )
    mir.assert_sealed()
    result = CanonicalSemanticSealV1(
        mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        binding_count=len(mir.bindings),
        seal_digest=_canonical_seal_digest(
            mir.fingerprint,
            mir.universe_plan_digest,
            len(mir.bindings),
        ),
    )
    result.assert_sealed()
    return result


def _representation_digest(
    *,
    seal: CanonicalSemanticSealV1,
    surface: NyrSurfaceV2,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    veil_key: bytes,
) -> str:
    key = _require_key(veil_key, field="representation veil key")
    material = b"\n".join(
        (
            seal.seal_digest.encode("ascii"),
            surface.surface_digest.encode("ascii"),
            veyra.digest.encode("ascii"),
            envelope.observer_id.encode("utf-8"),
            envelope.session_digest.hex().encode("ascii"),
            str(surface.visibility_epoch).encode("ascii"),
            str(surface.expires_before_epoch).encode("ascii"),
        )
    )
    return hmac.new(
        key,
        _CTX + b"observable-representation\x00" + material,
        hashlib.sha256,
    ).hexdigest()


def issue_observable_representation_v1(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> ObservableRepresentationV1:
    """Create an epoch/session-bound observable representation.

    The canonical seal participates only through keyed binding material and is
    not carried on the observer-facing object.
    """

    seal = seal_canonical_semantics_v1(mir)
    veyra.assert_sealed()
    surface = project_native_mir_nyr_v2(
        mir,
        veyra,
        envelope,
        veil_key=veil_key,
    )
    return ObservableRepresentationV1(
        surface=surface,
        visibility_epoch=surface.visibility_epoch,
        expires_before_epoch=surface.expires_before_epoch,
        representation_digest=_representation_digest(
            seal=seal,
            surface=surface,
            veyra=veyra,
            envelope=envelope,
            veil_key=veil_key,
        ),
    )


def require_representation_equivalence_v1(
    representation: ObservableRepresentationV1,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> None:
    """Prove that the visible representation came from these hidden inputs."""

    if not isinstance(representation, ObservableRepresentationV1):
        raise RepresentationBoundaryV1Error(
            "observable representation v1 required"
        )
    expected = issue_observable_representation_v1(
        mir,
        veyra,
        envelope,
        veil_key=veil_key,
    )
    if representation != expected:
        raise RepresentationBoundaryV1Error(
            "observable representation is not equivalent to hidden canonical state"
        )


def _grant_context_digest(
    *,
    seal: CanonicalSemanticSealV1,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    grant_id: str,
    purpose: str,
) -> str:
    payload = "\n".join(
        (
            f"grant={grant_id}",
            f"purpose={purpose}",
            f"canonical={seal.seal_digest}",
            f"veyra={veyra.digest}",
            f"observer={envelope.observer_id}",
            f"session={envelope.session_digest.hex()}",
            f"epoch={envelope.visibility_epoch}",
            f"expires-before={envelope.visibility_epoch + 1}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"reconstruction-context\x00" + payload).hexdigest()


def mint_reconstruction_grant_v1(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    grant_id: str,
    purpose: str,
    reconstruction_key: bytes,
) -> ReconstructionGrantV1:
    """Mint an exact one-epoch reconstruction capability."""

    if not grant_id.strip():
        raise RepresentationBoundaryV1Error("grant id must be non-empty")
    if not purpose.strip():
        raise RepresentationBoundaryV1Error("reconstruction purpose must be non-empty")
    if not isinstance(envelope, AdaptiveVisibilityEnvelopeV0):
        raise RepresentationBoundaryV1Error("adaptive visibility envelope required")
    if envelope.authority or not envelope.allowed:
        raise RepresentationBoundaryV1Error(
            "reconstruction grant requires allowed authority-free visibility context"
        )
    key = _require_key(reconstruction_key, field="reconstruction key")
    seal = seal_canonical_semantics_v1(mir)
    veyra.assert_sealed()
    context_digest = _grant_context_digest(
        seal=seal,
        veyra=veyra,
        envelope=envelope,
        grant_id=grant_id,
        purpose=purpose,
    )
    authorization_mac = hmac.new(
        key,
        _CTX + b"reconstruction-grant\x00" + context_digest.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return ReconstructionGrantV1(
        grant_id=grant_id,
        purpose=purpose,
        visibility_epoch=envelope.visibility_epoch,
        expires_before_epoch=envelope.visibility_epoch + 1,
        context_digest=context_digest,
        authorization_mac=authorization_mac,
    )


def reconstruct_canonical_semantics_v1(
    representation: ObservableRepresentationV1,
    hidden_mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    grant: ReconstructionGrantV1,
    *,
    purpose: str,
    current_epoch: int,
    veil_key: bytes,
    reconstruction_key: bytes,
) -> NativeSigilMir:
    """Authorize trusted re-materialization of canonical semantics.

    This does *not* invert the Nyr surface. The trusted runtime already owns the
    sealed canonical MIR; the grant only decides whether that hidden state may
    be re-materialized for this exact representation context.
    """

    representation.assert_live(current_epoch=current_epoch)
    require_representation_equivalence_v1(
        representation,
        hidden_mir,
        veyra,
        envelope,
        veil_key=veil_key,
    )
    if purpose != grant.purpose:
        raise RepresentationBoundaryV1Error("reconstruction purpose mismatch")
    if grant.visibility_epoch != representation.visibility_epoch:
        raise RepresentationBoundaryV1Error("reconstruction grant epoch mismatch")
    if grant.expires_before_epoch != representation.expires_before_epoch:
        raise RepresentationBoundaryV1Error("reconstruction grant expiry mismatch")
    if current_epoch >= grant.expires_before_epoch:
        raise RepresentationBoundaryV1Error("reconstruction grant expired")

    expected = mint_reconstruction_grant_v1(
        hidden_mir,
        veyra,
        envelope,
        grant_id=grant.grant_id,
        purpose=purpose,
        reconstruction_key=reconstruction_key,
    )
    if not hmac.compare_digest(grant.context_digest, expected.context_digest):
        raise RepresentationBoundaryV1Error(
            "reconstruction grant context mismatch"
        )
    if not hmac.compare_digest(
        grant.authorization_mac,
        expected.authorization_mac,
    ):
        raise RepresentationBoundaryV1Error(
            "reconstruction grant authorization mismatch"
        )
    hidden_mir.assert_sealed()
    return hidden_mir
