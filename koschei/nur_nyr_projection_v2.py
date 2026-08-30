"""Nur-controlled non-faithful Nyr projection v2.

Nyr v2 is an observer-facing, epoch-bounded projection of compiler-sealed native
MIR. Unlike the legacy v1 surface, it does not carry canonical sigil names,
canonical subjects, Veyra identity, Aevra identity, authority, or a topology
relation graph. Both the semantic-root label and subject label are projected to
observer/session/epoch/Veyra-bound aliases.

Projection integrity and runtime liveness are deliberately separate. A correctly
generated surface from an old epoch remains authentic history but is not a current
observer surface and cannot be replayed through sanctioned live boundaries.

This does not make the canonical world unknowable in a cryptographic sense. It
removes a direct faithful runtime projection and shortens the reuse lifetime of
what an observer can collect. Knowledge remains non-authoritative even if other
channels leak canonical facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir

_CTX = b"koschei.nur-nyr-projection/v2\x00"


class NyrProjectionV2Error(ValueError):
    pass


class NyrProjectionV2ReplayError(NyrProjectionV2Error):
    """Authentic Nyr surface presented outside its live visibility epoch."""


@dataclass(frozen=True, slots=True)
class NyrBindingV2:
    root_alias: str
    subject_alias: str


@dataclass(frozen=True, slots=True)
class NyrSurfaceV2:
    bindings: tuple[NyrBindingV2, ...]
    visibility_epoch: int
    expires_before_epoch: int
    surface_digest: str
    version: int = 2

    def render(self) -> str:
        return "\n".join(
            f"{item.root_alias} {item.subject_alias};"
            for item in self.bindings
        )


def _require_veil_key(veil_key: bytes) -> bytes:
    if not isinstance(veil_key, bytes) or len(veil_key) < 32:
        raise NyrProjectionV2Error("Nyr v2 veil key must contain at least 32 bytes")
    return veil_key


def _require_runtime_epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NyrProjectionV2Error(
            "current visibility epoch must be a non-negative integer"
        )
    return value


def _alias(
    *,
    domain: bytes,
    prefix: str,
    veil_key: bytes,
    veyra: VeyraIdentity,
    mir: NativeSigilMir,
    envelope: AdaptiveVisibilityEnvelopeV0,
    canonical_value: str,
    ordinal: int,
) -> str:
    material = b"\n".join(
        (
            veyra.digest.encode("ascii"),
            mir.fingerprint.encode("ascii"),
            envelope.observer_id.encode("utf-8"),
            envelope.session_digest.hex().encode("ascii"),
            envelope.compartment_seed_digest.hex().encode("ascii"),
            str(envelope.visibility_epoch).encode("ascii"),
            str(ordinal).encode("ascii"),
            canonical_value.encode("utf-8"),
        )
    )
    return prefix + hmac.new(
        veil_key,
        _CTX + domain + b"\x00" + material,
        hashlib.sha256,
    ).hexdigest()[:24]


def _surface_digest(
    bindings: tuple[NyrBindingV2, ...],
    epoch: int,
    expiry: int,
) -> str:
    rows = [f"epoch={epoch}", f"expires-before={expiry}"]
    rows.extend(
        f"binding={item.root_alias}:{item.subject_alias}"
        for item in bindings
    )
    return hashlib.sha256(
        _CTX + b"surface\x00" + "\n".join(rows).encode("utf-8")
    ).hexdigest()


def project_native_mir_nyr_v2(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> NyrSurfaceV2:
    """Project sealed native MIR without canonical root/subject labels."""

    mir.assert_sealed()
    veyra.assert_sealed()
    key = _require_veil_key(veil_key)
    if not isinstance(envelope, AdaptiveVisibilityEnvelopeV0) or envelope.authority:
        raise NyrProjectionV2Error("authority-free Nur visibility envelope required")
    if not envelope.allowed:
        raise NyrProjectionV2Error("contained Nur envelope exposes no Nyr v2 surface")
    if envelope.root_budget < len(mir.bindings):
        raise NyrProjectionV2Error("Nur root budget is too small for this Nyr v2 projection")

    bindings = tuple(
        NyrBindingV2(
            root_alias=_alias(
                domain=b"root",
                prefix="r",
                veil_key=key,
                veyra=veyra,
                mir=mir,
                envelope=envelope,
                canonical_value=item.sigil,
                ordinal=ordinal,
            ),
            subject_alias=_alias(
                domain=b"subject",
                prefix="n",
                veil_key=key,
                veyra=veyra,
                mir=mir,
                envelope=envelope,
                canonical_value=item.subject,
                ordinal=ordinal,
            ),
        )
        for ordinal, item in enumerate(mir.bindings)
    )
    epoch = envelope.visibility_epoch
    expiry = epoch + 1
    return NyrSurfaceV2(
        bindings=bindings,
        visibility_epoch=epoch,
        expires_before_epoch=expiry,
        surface_digest=_surface_digest(bindings, epoch, expiry),
    )


def require_nyr_surface_v2(
    surface: NyrSurfaceV2,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> None:
    """Verify projection integrity against hidden canonical inputs.

    This verifies that a visible surface is the exact projection of the supplied
    living inputs. Call :func:`require_live_nyr_surface_v2` at execution or
    observation boundaries where replay of an expired projection must fail.
    """

    expected = project_native_mir_nyr_v2(
        mir,
        veyra,
        envelope,
        veil_key=veil_key,
    )
    if surface != expected:
        raise NyrProjectionV2Error("Nyr v2 surface does not match living Galaxy projection")


def require_live_nyr_surface_v2(
    surface: NyrSurfaceV2,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
    current_visibility_epoch: int,
) -> None:
    """Fail closed unless a Nyr v2 surface is both authentic and currently live.

    The execution/observation boundary supplies the current visibility epoch.
    A surface is valid only in its birth epoch and expires before the next epoch.
    This makes an old, correctly generated Nyr surface non-reusable after epoch
    rotation instead of treating integrity as equivalent to liveness.
    """

    if not isinstance(current_visibility_epoch, int) or current_visibility_epoch < 0:
        raise NyrProjectionV2Error("current visibility epoch must be a non-negative integer")
    require_nyr_surface_v2(surface, mir, veyra, envelope, veil_key=veil_key)
    if surface.expires_before_epoch != surface.visibility_epoch + 1:
        raise NyrProjectionV2Error("Nyr v2 surface carries an invalid expiry boundary")
    if current_visibility_epoch != surface.visibility_epoch:
        if current_visibility_epoch >= surface.expires_before_epoch:
            raise NyrProjectionV2Error("Nyr v2 surface has expired and cannot be replayed")
        raise NyrProjectionV2Error("Nyr v2 surface is not valid for the current visibility epoch")
