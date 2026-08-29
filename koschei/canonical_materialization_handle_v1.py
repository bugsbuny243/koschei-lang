"""Opaque canonical-materialization handles for Koschei representation separation v1.

A sanctioned reconstruction must not hand `NativeSigilMir` back to the broad runtime.
This module keeps the hidden MIR inside a trusted in-process registry and returns an
opaque, scoped, epoch-bound handle instead.  The sanctioned native-effect gate consumes
that handle atomically, resolves the hidden MIR only inside the trusted boundary, runs
Koschei native proof enforcement, and exposes only the effect intent/result outside.

This Python bootstrap cannot provide process isolation: arbitrary code that can inspect
this registry object or import private helpers can still reach trusted state.  Native
runtime compartments must make the registry and raw MIR physically inaccessible to the
observer/runtime surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import Lock
from typing import Callable, TypeVar

from .native_sigil_enforcement_gate_v1 import (
    EnforcementDecision,
    PrivilegedEffectIntent,
    enforce_effect,
)
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .representation_boundary_v1 import seal_canonical_semantics_v1

_CTX = b"koschei.canonical-materialization-handle/v1\x00"
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


def _handle_payload(
    *,
    handle_id: str,
    purpose: str,
    issued_epoch: int,
    expires_before_epoch: int,
    reconstruction_receipt_digest: str,
) -> bytes:
    rows = (
        f"handle={handle_id}",
        f"purpose={purpose}",
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
    """Observer/runtime-safe reference to hidden canonical state.

    The handle deliberately carries no MIR fingerprint, Universe-plan digest, sigil name,
    canonical subject, semantic-domain label, Veyra identity or canonical seal digest.
    """

    handle_id: str
    purpose: str
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
    purpose: str
    issued_epoch: int
    expires_before_epoch: int
    reconstruction_receipt_digest: str


class CanonicalMaterializationRegistryV1:
    """Trusted in-process custody for hidden canonical MIR.

    Entries are addressed only by random opaque handles and removed before sanctioned
    effect enforcement begins.  This gives one-shot semantics inside one authoritative
    registry, not durable/global replay resistance.
    """

    def __init__(self, *, materialization_key: bytes) -> None:
        self._key = _key(materialization_key)
        self._lock = Lock()
        self._entries: dict[str, _MaterializationEntryV1] = {}

    def mint(
        self,
        *,
        hidden_mir: NativeSigilMir,
        canonical_seal_digest: str,
        purpose: str,
        issued_epoch: int,
        expires_before_epoch: int,
        reconstruction_receipt_digest: str,
    ) -> CanonicalMaterializationHandleV1:
        hidden_mir.assert_sealed()
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
        receipt_digest = _text(
            reconstruction_receipt_digest, "reconstruction_receipt_digest"
        )
        with self._lock:
            while True:
                handle_id = secrets.token_hex(32)
                if handle_id not in self._entries:
                    break
            handle = CanonicalMaterializationHandleV1(
                handle_id=handle_id,
                purpose=purpose_value,
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
                purpose=purpose_value,
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
        current_epoch: int,
    ) -> NativeSigilMir:
        """Trusted-only primitive used by sanctioned effect gates."""

        if not isinstance(handle, CanonicalMaterializationHandleV1):
            raise CanonicalMaterializationHandleV1Error(
                "canonical materialization handle v1 required"
            )
        handle.assert_authenticated(materialization_key=self._key)
        requested_purpose = _text(purpose, "purpose")
        current = _epoch(current_epoch)
        if requested_purpose != handle.purpose:
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle purpose mismatch"
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
                entry.purpose != handle.purpose
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
            # Consume before evaluation/effect execution. Failure after this point burns the
            # handle rather than leaving a reusable canonical-world capability.
            del self._entries[handle.handle_id]
        hidden.assert_sealed()
        return hidden


EpochSource = Callable[[], int]


@dataclass(frozen=True, slots=True)
class CanonicalMaterializationEffectGateV1:
    """Sanctioned one-shot bridge from an opaque handle to one native effect decision."""

    registry: CanonicalMaterializationRegistryV1
    handle: CanonicalMaterializationHandleV1
    proof: NativeSigilProofBundle
    intent: PrivilegedEffectIntent
    epoch_source: EpochSource
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
        if not callable(self.epoch_source):
            raise CanonicalMaterializationHandleV1Error(
                "trusted materialization epoch source must be callable"
            )
        _text(self.purpose, "purpose")

    def execute(
        self,
        effect: Callable[[PrivilegedEffectIntent], _T],
    ) -> tuple[EnforcementDecision, _T | None]:
        try:
            current = _epoch(self.epoch_source())
        except CanonicalMaterializationHandleV1Error:
            raise
        except Exception as exc:
            raise CanonicalMaterializationHandleV1Error(
                "trusted materialization epoch source failed closed"
            ) from exc
        hidden_mir = self.registry._consume_hidden_mir(
            self.handle,
            purpose=self.purpose,
            current_epoch=current,
        )
        return enforce_effect(hidden_mir, self.proof, self.intent, effect)
