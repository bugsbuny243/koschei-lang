"""Trusted single-use reconstruction boundary for representation separation v1.

`representation_boundary_v1` defines the low-level semantic relation between hidden
canonical MIR, observer-safe representation and reconstruction grants. This module is
the sanctioned runtime-side consumption boundary: epoch truth comes from a trusted
source, one exact reconstruction grant context can cross back into the canonical world
at most once per authoritative ledger, and the broad runtime receives only an opaque
materialization handle rather than the canonical MIR object itself.

The Python prototype cannot prevent callers from importing lower-level helpers directly.
Native/runtime APIs must expose this gate and keep raw MIR/reconstruction primitives in a
trusted compartment when representation separation is a security invariant.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from threading import Lock
from typing import Callable

from .canonical_materialization_handle_v1 import (
    CanonicalMaterializationHandleV1,
    CanonicalMaterializationRegistryV1,
)
from .galaxy_identity_v1 import VeyraIdentity
from .library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from .native_sigil_mir_v1 import NativeSigilMir
from .representation_boundary_v1 import (
    ObservableRepresentationV1,
    ReconstructionGrantV1,
    RepresentationBoundaryV1Error,
    reconstruct_canonical_semantics_v1,
    seal_canonical_semantics_v1,
)

_CTX = b"koschei.representation-reconstruction-gate/v1\x00"


class RepresentationReconstructionGateV1Error(ValueError):
    pass


EpochSource = Callable[[], int]


def _require_key(value: bytes, *, field: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise RepresentationReconstructionGateV1Error(
            f"{field} must contain at least 32 bytes"
        )
    return value


def _require_epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RepresentationReconstructionGateV1Error(
            "trusted epoch source returned an invalid epoch"
        )
    return value


def _receipt_payload(
    *,
    grant_context_digest: str,
    representation_digest: str,
    canonical_seal_digest: str,
    purpose: str,
    consumed_epoch: int,
) -> bytes:
    rows = (
        f"grant-context={grant_context_digest}",
        f"representation={representation_digest}",
        f"canonical-seal={canonical_seal_digest}",
        f"purpose={purpose}",
        f"consumed-epoch={consumed_epoch}",
        "single-use=1",
        "authority=0",
        "version=1",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ReconstructionConsumptionReceiptV1:
    """Trusted-side proof that one reconstruction grant context was consumed."""

    grant_context_digest: str
    representation_digest: str
    canonical_seal_digest: str
    purpose: str
    consumed_epoch: int
    receipt_digest: str
    single_use: bool = True
    authority: bool = False
    version: int = 1

    def assert_authenticated(self, *, receipt_key: bytes) -> None:
        key = _require_key(receipt_key, field="reconstruction receipt key")
        if self.version != 1:
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption receipt requires version 1"
            )
        if self.single_use is not True:
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption receipt must remain single-use"
            )
        if self.authority is not False:
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption receipt cannot carry ambient authority"
            )
        epoch = _require_epoch(self.consumed_epoch)
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption purpose cannot be empty"
            )
        expected = hmac.new(
            key,
            _receipt_payload(
                grant_context_digest=self.grant_context_digest,
                representation_digest=self.representation_digest,
                canonical_seal_digest=self.canonical_seal_digest,
                purpose=self.purpose,
                consumed_epoch=epoch,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(self.receipt_digest, expected):
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption receipt authentication failed"
            )


class ReconstructionConsumptionLedgerV1:
    """Atomic in-process single-use state for reconstruction grant contexts.

    This is deliberately a bootstrap ledger. It prevents concurrent/repeated use in
    one authoritative process, but it is not durable, shared, rollback-safe or fork-safe.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._consumed_contexts: set[str] = set()

    def consume(
        self,
        *,
        grant: ReconstructionGrantV1,
        representation: ObservableRepresentationV1,
        hidden_mir: NativeSigilMir,
        purpose: str,
        consumed_epoch: int,
        receipt_key: bytes,
    ) -> ReconstructionConsumptionReceiptV1:
        key = _require_key(receipt_key, field="reconstruction receipt key")
        epoch = _require_epoch(consumed_epoch)
        if grant.version != 1:
            raise RepresentationReconstructionGateV1Error(
                "reconstruction grant requires version 1"
            )
        if representation.version != 1:
            raise RepresentationReconstructionGateV1Error(
                "observable representation requires version 1"
            )
        if not isinstance(purpose, str) or not purpose.strip():
            raise RepresentationReconstructionGateV1Error(
                "reconstruction purpose cannot be empty"
            )
        seal = seal_canonical_semantics_v1(hidden_mir)
        context = grant.context_digest
        with self._lock:
            if context in self._consumed_contexts:
                raise RepresentationReconstructionGateV1Error(
                    "reconstruction grant context already consumed"
                )
            self._consumed_contexts.add(context)
            receipt = ReconstructionConsumptionReceiptV1(
                grant_context_digest=context,
                representation_digest=representation.representation_digest,
                canonical_seal_digest=seal.seal_digest,
                purpose=purpose,
                consumed_epoch=epoch,
                receipt_digest="",
            )
            object.__setattr__(
                receipt,
                "receipt_digest",
                hmac.new(
                    key,
                    _receipt_payload(
                        grant_context_digest=receipt.grant_context_digest,
                        representation_digest=receipt.representation_digest,
                        canonical_seal_digest=receipt.canonical_seal_digest,
                        purpose=receipt.purpose,
                        consumed_epoch=receipt.consumed_epoch,
                    ),
                    hashlib.sha256,
                ).hexdigest(),
            )
        receipt.assert_authenticated(receipt_key=key)
        return receipt


@dataclass(frozen=True, slots=True)
class RepresentationReconstructionGateV1:
    """Trusted runtime gate for one hidden/observable representation context."""

    representation: ObservableRepresentationV1
    hidden_mir: NativeSigilMir
    veyra: VeyraIdentity
    envelope: AdaptiveVisibilityEnvelopeV0
    grant: ReconstructionGrantV1
    veil_key: bytes
    reconstruction_key: bytes
    receipt_key: bytes
    epoch_source: EpochSource
    ledger: ReconstructionConsumptionLedgerV1
    materialization_registry: CanonicalMaterializationRegistryV1

    def __post_init__(self) -> None:
        self.hidden_mir.assert_sealed()
        self.veyra.assert_sealed()
        if not isinstance(self.representation, ObservableRepresentationV1):
            raise RepresentationReconstructionGateV1Error(
                "observable representation v1 required"
            )
        if not isinstance(self.grant, ReconstructionGrantV1):
            raise RepresentationReconstructionGateV1Error(
                "reconstruction grant v1 required"
            )
        if not isinstance(self.envelope, AdaptiveVisibilityEnvelopeV0):
            raise RepresentationReconstructionGateV1Error(
                "adaptive visibility envelope required"
            )
        if self.envelope.authority or not self.envelope.allowed:
            raise RepresentationReconstructionGateV1Error(
                "reconstruction gate requires allowed authority-free visibility context"
            )
        _require_key(self.veil_key, field="representation veil key")
        _require_key(self.reconstruction_key, field="reconstruction key")
        _require_key(self.receipt_key, field="reconstruction receipt key")
        if not callable(self.epoch_source):
            raise RepresentationReconstructionGateV1Error(
                "trusted epoch source must be callable"
            )
        if not isinstance(self.ledger, ReconstructionConsumptionLedgerV1):
            raise RepresentationReconstructionGateV1Error(
                "reconstruction consumption ledger v1 required"
            )
        if not isinstance(
            self.materialization_registry, CanonicalMaterializationRegistryV1
        ):
            raise RepresentationReconstructionGateV1Error(
                "canonical materialization registry v1 required"
            )

    def reconstruct(
        self, *, purpose: str
    ) -> tuple[CanonicalMaterializationHandleV1, ReconstructionConsumptionReceiptV1]:
        """Authorize reconstruction, consume the grant, and return only an opaque handle."""

        try:
            current_epoch = _require_epoch(self.epoch_source())
        except RepresentationReconstructionGateV1Error:
            raise
        except Exception as exc:
            raise RepresentationReconstructionGateV1Error(
                "trusted epoch source failed closed"
            ) from exc

        try:
            hidden = reconstruct_canonical_semantics_v1(
                self.representation,
                self.hidden_mir,
                self.veyra,
                self.envelope,
                self.grant,
                purpose=purpose,
                current_epoch=current_epoch,
                veil_key=self.veil_key,
                reconstruction_key=self.reconstruction_key,
            )
        except RepresentationBoundaryV1Error as exc:
            raise RepresentationReconstructionGateV1Error(str(exc)) from exc

        receipt = self.ledger.consume(
            grant=self.grant,
            representation=self.representation,
            hidden_mir=hidden,
            purpose=purpose,
            consumed_epoch=current_epoch,
            receipt_key=self.receipt_key,
        )
        handle = self.materialization_registry.mint(
            hidden_mir=hidden,
            canonical_seal_digest=receipt.canonical_seal_digest,
            purpose=purpose,
            issued_epoch=current_epoch,
            expires_before_epoch=self.grant.expires_before_epoch,
            reconstruction_receipt_digest=receipt.receipt_digest,
        )
        return handle, receipt
