"""Opaque canonical-materialization handles for Koschei representation separation v1.

A sanctioned reconstruction must not hand `NativeSigilMir` back to the broad runtime.
This module keeps hidden MIR inside a trusted in-process registry and returns an opaque,
scoped, epoch-bound handle. The handle is bound to one exact sealed
`CanonicalEffectRequest`, but it exposes only a keyed opaque request binding rather than
the canonical request digest itself.

The sanctioned effect gate consumes the handle atomically, resolves hidden MIR only
inside the trusted boundary, verifies the request-bound native proof, and exposes only
the canonical request/effect result outside. Its liveness decision comes from the same
`ContinuityEpochAuthorityV1` contract used by Nyr observation and reconstruction.

This Python bootstrap cannot provide process isolation: arbitrary code that can inspect
this registry object or import private helpers can still reach trusted state. Native
runtime compartments must make registry internals and raw MIR physically inaccessible to
the observer/runtime surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import Lock
from typing import Callable, TypeVar

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import (
    CanonicalEffectRequest,
    RequestBoundProof,
    enforce_bound_effect,
)
from .representation_boundary_v1 import seal_canonical_semantics_v1

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


def _request_binding(key: bytes, canonical_request_digest: str) -> str:
    digest = _text(canonical_request_digest, "canonical_request_digest")
    return hmac.new(key, _REQUEST_CTX + digest.encode("ascii"), hashlib.sha256).hexdigest()


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
    """Runtime-safe capability reference to one hidden semantic world/request pair.

    The handle deliberately carries no MIR fingerprint, Universe-plan digest, sigil name,
    canonical subject, semantic-domain label, Veyra identity, canonical seal digest or raw
    canonical-request digest.
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
    purpose: str
    canonical_request_digest: str
    request_binding_digest: str
    issued_epoch: int
    expires_before_epoch: int
    reconstruction_receipt_digest: str


class CanonicalMaterializationRegistryV1:
    """Trusted in-process custody for hidden canonical MIR.

    Entries are addressed only by random opaque handles and removed before sanctioned
    request-bound effect enforcement begins. This gives one-shot semantics inside one
    authoritative registry, not durable/global replay resistance.
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
        canonical_request: CanonicalEffectRequest,
        purpose: str,
        issued_epoch: int,
        expires_before_epoch: int,
        reconstruction_receipt_digest: str,
    ) -> CanonicalMaterializationHandleV1:
        hidden_mir.assert_sealed()
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
        request_binding = _request_binding(self._key, canonical_request.digest)
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
        current_epoch: int,
    ) -> NativeSigilMir:
        """Trusted-only primitive used by sanctioned request-bound effect gates."""

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
        expected_request_binding = _request_binding(self._key, canonical_request.digest)
        if not hmac.compare_digest(
            expected_request_binding, handle.request_binding_digest
        ):
            raise CanonicalMaterializationHandleV1Error(
                "materialization handle canonical request mismatch"
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
                entry.purpose != handle.purpose
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
            # Consume after exact request/world verification but before proof/effect
            # evaluation. Later failure burns the capability rather than leaving reusable
            # canonical access.
            del self._entries[handle.handle_id]
        hidden.assert_sealed()
        return hidden


@dataclass(frozen=True, slots=True)
class CanonicalMaterializationEffectGateV1:
    """One-shot bridge from opaque handle to one exact request-bound native effect."""

    registry: CanonicalMaterializationRegistryV1
    handle: CanonicalMaterializationHandleV1
    request: CanonicalEffectRequest
    proof: NativeSigilProofBundle
    bound: RequestBoundProof
    continuity: ContinuityEpochAuthorityV1
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
        if not isinstance(self.continuity, ContinuityEpochAuthorityV1):
            raise CanonicalMaterializationHandleV1Error(
                "Continuity epoch authority v1 required"
            )
        self.continuity.assert_sealed()
        _text(self.purpose, "purpose")

    def execute(
        self,
        effect: Callable[[CanonicalEffectRequest], _T],
    ) -> tuple[EnforcementDecision, _T | None]:
        current = self.continuity.current_epoch()
        hidden_mir = self.registry._consume_hidden_mir(
            self.handle,
            purpose=self.purpose,
            canonical_request=self.request,
            current_epoch=current,
        )
        return enforce_bound_effect(
            hidden_mir,
            self.request,
            self.proof,
            self.bound,
            effect,
        )
