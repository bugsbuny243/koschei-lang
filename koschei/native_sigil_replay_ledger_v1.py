"""Replay-safe consumption ledger for native Koschei privileged effects v1.

Request binding proves that a proof belongs to one exact request.  It does not by
itself prove that the same exact request has not already been executed.  This
module adds the consumption boundary: an ALLOW request is claimed exactly once
before the privileged callback is invoked, then committed or marked uncertain.

The in-memory ledger is deliberately a reference implementation.  Production
backends must preserve the same atomic claim/commit semantics in durable storage.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import RLock
from typing import Callable, Generic, TypeVar

from .native_sigil_enforcement_gate_v1 import EnforcementDecision
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import (
    CanonicalEffectRequest,
    RequestBoundProof,
    enforce_bound_effect,
)

_CTX = b"koschei.native-sigil-replay-ledger/v1\x00"
_T = TypeVar("_T")


class NativeSigilReplayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    request_digest: str
    effect_id: str
    epoch: int
    state: str
    proof_digest: str
    decision_digest: str
    digest: str


class ReplayLedger(Generic[_T]):
    """Atomic in-process claim ledger for the reference enforcement path."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, ReplayRecord] = {}

    def get(self, request_digest: str) -> ReplayRecord | None:
        with self._lock:
            return self._records.get(request_digest)

    def _record(
        self,
        *,
        request: CanonicalEffectRequest,
        proof_digest: str,
        decision_digest: str,
        state: str,
    ) -> ReplayRecord:
        digest = _record_digest(
            request.digest,
            request.effect_id,
            request.epoch,
            state,
            proof_digest,
            decision_digest,
        )
        record = ReplayRecord(
            request_digest=request.digest,
            effect_id=request.effect_id,
            epoch=request.epoch,
            state=state,
            proof_digest=proof_digest,
            decision_digest=decision_digest,
            digest=digest,
        )
        self._records[request.digest] = record
        return record

    def claim(
        self,
        request: CanonicalEffectRequest,
        proof_digest: str,
    ) -> ReplayRecord:
        """Atomically reserve an exact request before privileged execution."""
        with self._lock:
            existing = self._records.get(request.digest)
            if existing is not None:
                raise NativeSigilReplayError(
                    f"privileged request already consumed or in-flight: {existing.state}"
                )
            return self._record(
                request=request,
                proof_digest=proof_digest,
                decision_digest="pending",
                state="CLAIMED",
            )

    def finalize(
        self,
        request: CanonicalEffectRequest,
        proof_digest: str,
        decision: EnforcementDecision,
        *,
        state: str,
    ) -> ReplayRecord:
        if state not in {"COMMITTED", "REJECTED", "CONTAINED", "UNCERTAIN"}:
            raise NativeSigilReplayError(f"invalid replay final state: {state}")
        with self._lock:
            current = self._records.get(request.digest)
            if current is None or current.state != "CLAIMED":
                raise NativeSigilReplayError("request was not atomically claimed")
            if current.proof_digest != proof_digest:
                raise NativeSigilReplayError("claimed proof digest changed before finality")
            return self._record(
                request=request,
                proof_digest=proof_digest,
                decision_digest=decision.digest,
                state=state,
            )


def _record_digest(
    request_digest: str,
    effect_id: str,
    epoch: int,
    state: str,
    proof_digest: str,
    decision_digest: str,
) -> str:
    payload = "\n".join(
        (
            f"request={request_digest}",
            f"effect={effect_id}",
            f"epoch={epoch}",
            f"state={state}",
            f"proof={proof_digest}",
            f"decision={decision_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def enforce_once(
    ledger: ReplayLedger[_T],
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    bound: RequestBoundProof,
    effect: Callable[[CanonicalEffectRequest], _T],
) -> tuple[EnforcementDecision, _T | None, ReplayRecord]:
    """Consume one exact request at most once across the reference process.

    The request is claimed before evaluation/effect invocation.  DENY and CONTAIN
    are terminal consumed outcomes too, preventing a caller from replaying the
    same exact request until a later attempt happens to observe different state.

    If the privileged callback raises after ALLOW, the ledger records UNCERTAIN
    rather than releasing the request.  Retrying blindly could duplicate an
    external side effect whose completion is unknown.
    """

    request.assert_sealed(mir)
    bound.assert_sealed(mir, request, proof)
    ledger.claim(request, proof.digest)

    try:
        decision, result = enforce_bound_effect(mir, request, proof, bound, effect)
    except Exception:
        # We do not know whether an external effect occurred before the exception.
        placeholder = EnforcementDecision(
            decision="CONTAIN",
            effect_id=request.effect_id,
            native_mir_fingerprint=mir.fingerprint,
            proof_digest=proof.digest,
            failed_obligations=("effect-finality-uncertain",),
            digest="",
        )
        object.__setattr__(
            placeholder,
            "digest",
            hashlib.sha256(
                _CTX
                + b"uncertain\x00"
                + "\n".join(
                    (
                        request.digest,
                        proof.digest,
                        mir.fingerprint,
                    )
                ).encode("utf-8")
            ).hexdigest(),
        )
        record = ledger.finalize(
            request,
            proof.digest,
            placeholder,
            state="UNCERTAIN",
        )
        raise NativeSigilReplayError(
            f"privileged effect finality is uncertain; request tombstoned: {record.digest}"
        )

    state = {
        "ALLOW": "COMMITTED",
        "DENY": "REJECTED",
        "CONTAIN": "CONTAINED",
    }[decision.decision]
    record = ledger.finalize(
        request,
        proof.digest,
        decision,
        state=state,
    )
    return decision, result, record
