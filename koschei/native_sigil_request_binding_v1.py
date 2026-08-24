"""Request-bound enforcement for native Koschei sigil programs v1.

A valid Koschei proof must not be portable to a different privileged request.
This module seals a canonical effect request to compiler-produced native MIR and
then binds an already-verified NativeSigilProofBundle to that exact request.

The protected subject must be declared by a `vor` binding in the native MIR.
The request carries explicit identity, epoch and nonce/replay material so a
proof for one actor/request/epoch cannot be replayed as authority for another.
It is sealed to both the semantic Universe identity and the executable activation
plan identity so durable execution/epoch machinery observes the same reality.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, TypeVar

from .native_sigil_enforcement_gate_v1 import (
    EnforcementDecision,
    PrivilegedEffectIntent,
    enforce_effect,
)
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import (
    NativeSigilProofBundle,
    require_native_sigil_proof,
)
from .universe_activation_engine_v1 import compile_activation_plan

_CTX = b"koschei.native-sigil-request-binding/v1\x00"
_T = TypeVar("_T")


class NativeSigilRequestBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalEffectRequest:
    effect_id: str
    subject: str
    operation: str
    request_digest: str
    identity_digest: str
    epoch: int
    nonce_digest: str
    native_mir_fingerprint: str
    universe_plan_digest: str
    digest: str
    activation_plan_digest: str = ""
    version: int = 1

    def assert_sealed(self, mir: NativeSigilMir) -> None:
        mir.assert_sealed()
        if self.native_mir_fingerprint != mir.fingerprint:
            raise NativeSigilRequestBindingError("request MIR fingerprint mismatch")
        if self.universe_plan_digest != mir.universe_plan_digest:
            raise NativeSigilRequestBindingError("request Universe identity mismatch")
        expected_activation = compile_activation_plan(
            tuple(item.sigil for item in mir.bindings)
        ).digest
        if self.activation_plan_digest != expected_activation:
            raise NativeSigilRequestBindingError("request activation-plan identity mismatch")
        if self.epoch < 0:
            raise NativeSigilRequestBindingError("request epoch cannot be negative")
        vor_subjects = {item.subject for item in mir.bindings if item.sigil == "vor"}
        if self.subject not in vor_subjects:
            raise NativeSigilRequestBindingError(
                "privileged request subject is not declared by a vor binding"
            )
        expected = _request_digest(
            self.effect_id,
            self.subject,
            self.operation,
            self.request_digest,
            self.identity_digest,
            self.epoch,
            self.nonce_digest,
            self.native_mir_fingerprint,
            self.universe_plan_digest,
            self.activation_plan_digest,
        )
        if self.digest != expected:
            raise NativeSigilRequestBindingError("canonical effect request seal mismatch")


@dataclass(frozen=True, slots=True)
class RequestBoundProof:
    request_digest: str
    proof_digest: str
    native_mir_fingerprint: str
    universe_plan_digest: str
    decision: str
    digest: str
    version: int = 1

    def assert_sealed(
        self,
        mir: NativeSigilMir,
        request: CanonicalEffectRequest,
        proof: NativeSigilProofBundle,
    ) -> None:
        request.assert_sealed(mir)
        require_native_sigil_proof(mir, proof)
        if self.request_digest != request.digest:
            raise NativeSigilRequestBindingError("bound proof request mismatch")
        if self.proof_digest != proof.digest:
            raise NativeSigilRequestBindingError("bound proof proof-digest mismatch")
        if self.native_mir_fingerprint != mir.fingerprint:
            raise NativeSigilRequestBindingError("bound proof MIR mismatch")
        if self.universe_plan_digest != mir.universe_plan_digest:
            raise NativeSigilRequestBindingError("bound proof Universe mismatch")
        if self.decision != proof.decision:
            raise NativeSigilRequestBindingError("bound proof decision mismatch")
        expected = _bound_digest(
            self.request_digest,
            self.proof_digest,
            self.native_mir_fingerprint,
            self.universe_plan_digest,
            self.decision,
        )
        if self.digest != expected:
            raise NativeSigilRequestBindingError("request-bound proof seal mismatch")


def _request_digest(
    effect_id: str,
    subject: str,
    operation: str,
    payload_digest: str,
    identity_digest: str,
    epoch: int,
    nonce_digest: str,
    mir_fingerprint: str,
    universe_digest: str,
    activation_digest: str,
) -> str:
    values = (
        effect_id,
        subject,
        operation,
        payload_digest,
        identity_digest,
        str(epoch),
        nonce_digest,
        mir_fingerprint,
        universe_digest,
        activation_digest,
    )
    if any(not value for value in values):
        raise NativeSigilRequestBindingError("canonical effect request fields cannot be empty")
    payload = "\n".join(values).encode("utf-8")
    return hashlib.sha256(_CTX + b"request\x00" + payload).hexdigest()


def _bound_digest(
    request_digest: str,
    proof_digest: str,
    mir_fingerprint: str,
    universe_digest: str,
    decision: str,
) -> str:
    payload = "\n".join(
        (
            f"request={request_digest}",
            f"proof={proof_digest}",
            f"mir={mir_fingerprint}",
            f"universe={universe_digest}",
            f"decision={decision}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"bound-proof\x00" + payload).hexdigest()


def seal_effect_request(
    mir: NativeSigilMir,
    *,
    effect_id: str,
    subject: str,
    operation: str,
    request_digest: str,
    identity_digest: str,
    epoch: int,
    nonce_digest: str,
) -> CanonicalEffectRequest:
    mir.assert_sealed()
    activation_digest = compile_activation_plan(
        tuple(item.sigil for item in mir.bindings)
    ).digest
    result = CanonicalEffectRequest(
        effect_id=effect_id,
        subject=subject,
        operation=operation,
        request_digest=request_digest,
        identity_digest=identity_digest,
        epoch=epoch,
        nonce_digest=nonce_digest,
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        digest="",
        activation_plan_digest=activation_digest,
    )
    object.__setattr__(
        result,
        "digest",
        _request_digest(
            result.effect_id,
            result.subject,
            result.operation,
            result.request_digest,
            result.identity_digest,
            result.epoch,
            result.nonce_digest,
            result.native_mir_fingerprint,
            result.universe_plan_digest,
            result.activation_plan_digest,
        ),
    )
    result.assert_sealed(mir)
    return result


def bind_proof_to_request(
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
) -> RequestBoundProof:
    request.assert_sealed(mir)
    require_native_sigil_proof(mir, proof)
    result = RequestBoundProof(
        request_digest=request.digest,
        proof_digest=proof.digest,
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        decision=proof.decision,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _bound_digest(
            result.request_digest,
            result.proof_digest,
            result.native_mir_fingerprint,
            result.universe_plan_digest,
            result.decision,
        ),
    )
    result.assert_sealed(mir, request, proof)
    return result


def enforce_bound_effect(
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    bound: RequestBoundProof,
    effect: Callable[[CanonicalEffectRequest], _T],
) -> tuple[EnforcementDecision, _T | None]:
    """Run an effect only after proof, MIR and exact request are mutually sealed."""
    bound.assert_sealed(mir, request, proof)
    intent = PrivilegedEffectIntent(
        effect_id=request.effect_id,
        subject=request.subject,
        operation=request.operation,
        request_digest=request.request_digest,
    )

    def invoke(_: PrivilegedEffectIntent) -> _T:
        return effect(request)

    return enforce_effect(mir, proof, intent, invoke)
