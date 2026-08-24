"""Nur-controlled Nyr projection for native Koschei MIR v1.

A Nyr is an observer-facing, time-bounded projection of canonical native MIR. It
is not source, not Aevra, not Veyra and never grants authority. Canonical sigil
roots remain recognizable while subject aliases are derived from Veyra identity,
observer/session visibility state, epoch and an internal veil key.

The projection is produced from compiler-sealed MIR rather than by reinterpreting
raw source. A visible Nyr intentionally carries no canonical subject or Veyra
identifier that can be used as a topology map.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir

_CTX = b"koschei.nur-nyr-projection/v1\x00"


class NyrProjectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NyrBinding:
    sigil: str
    alias: str


@dataclass(frozen=True, slots=True)
class NyrSurface:
    bindings: tuple[NyrBinding, ...]
    visibility_epoch: int
    expires_before_epoch: int
    surface_digest: str
    version: int = 1

    def render(self) -> str:
        return "\n".join(f"{item.sigil} {item.alias};" for item in self.bindings)


def _require_veil_key(veil_key: bytes) -> bytes:
    if not isinstance(veil_key, bytes) or len(veil_key) < 32:
        raise NyrProjectionError("Nyr veil key must contain at least 32 bytes")
    return veil_key


def _alias(
    *,
    veil_key: bytes,
    veyra: VeyraIdentity,
    mir: NativeSigilMir,
    envelope: AdaptiveVisibilityEnvelopeV0,
    sigil: str,
    subject: str,
    ordinal: int,
) -> str:
    material = b"\n".join(
        (
            veyra.digest.encode("ascii"),
            mir.fingerprint.encode("ascii"),
            envelope.compartment_seed_digest.hex().encode("ascii"),
            str(envelope.visibility_epoch).encode("ascii"),
            str(ordinal).encode("ascii"),
            sigil.encode("utf-8"),
            subject.encode("utf-8"),
        )
    )
    # Prefix with a letter so the alias remains a valid Koschei identifier-like
    # surface without exposing the canonical subject name.
    return "n" + hmac.new(veil_key, _CTX + b"alias\x00" + material, hashlib.sha256).hexdigest()[:24]


def _surface_digest(bindings: tuple[NyrBinding, ...], epoch: int, expiry: int) -> str:
    rows = [f"epoch={epoch}", f"expires-before={expiry}"]
    rows.extend(f"binding={item.sigil}:{item.alias}" for item in bindings)
    return hashlib.sha256(_CTX + b"surface\x00" + "\n".join(rows).encode("utf-8")).hexdigest()


def project_native_mir_nyr(
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> NyrSurface:
    """Project sealed native MIR into one observer/epoch-specific Nyr surface."""

    mir.assert_sealed()
    veyra.assert_sealed()
    key = _require_veil_key(veil_key)
    if not isinstance(envelope, AdaptiveVisibilityEnvelopeV0) or envelope.authority:
        raise NyrProjectionError("authority-free Nur visibility envelope required")
    if not envelope.allowed:
        raise NyrProjectionError("contained Nur envelope exposes no Nyr surface")
    if envelope.root_budget < len(mir.bindings):
        raise NyrProjectionError("Nur root budget is too small for this Nyr projection")

    bindings = tuple(
        NyrBinding(
            sigil=item.sigil,
            alias=_alias(
                veil_key=key,
                veyra=veyra,
                mir=mir,
                envelope=envelope,
                sigil=item.sigil,
                subject=item.subject,
                ordinal=ordinal,
            ),
        )
        for ordinal, item in enumerate(mir.bindings)
    )
    epoch = envelope.visibility_epoch
    expiry = epoch + 1
    return NyrSurface(
        bindings=bindings,
        visibility_epoch=epoch,
        expires_before_epoch=expiry,
        surface_digest=_surface_digest(bindings, epoch, expiry),
    )


def require_nyr_surface(
    surface: NyrSurface,
    mir: NativeSigilMir,
    veyra: VeyraIdentity,
    envelope: AdaptiveVisibilityEnvelopeV0,
    *,
    veil_key: bytes,
) -> None:
    """Verify a Nyr against hidden canonical inputs without making it authority."""

    expected = project_native_mir_nyr(mir, veyra, envelope, veil_key=veil_key)
    if surface != expected:
        raise NyrProjectionError("Nyr surface does not match living Galaxy projection")
