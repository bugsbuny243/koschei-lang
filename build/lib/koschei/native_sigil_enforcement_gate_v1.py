"""Proof-bound enforcement gate for native Koschei sigil programs v1.

This is the first runtime boundary that can actually permit or suppress a
privileged effect based on compiler-produced native MIR plus a sealed Koschei
proof bundle. The gate never re-parses source and never trusts a caller-supplied
decision string without re-verifying the complete proof chain.

The gate deliberately separates three outcomes:

- ALLOW: every required Library obligation succeeded and the effect callback may run.
- DENY: proof is valid but one or more non-containment obligations failed.
- CONTAIN: proof is valid and the failed obligation belongs to a containment/
  recovery/finality safety domain where the caller must stop normal execution
  and enter the containing path.

No effect callback is invoked for DENY or CONTAIN.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Generic, TypeVar

from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import (
    NativeSigilProofBundle,
    require_native_sigil_proof,
)

_CTX = b"koschei.native-sigil-enforcement-gate/v1\x00"
_T = TypeVar("_T")


class NativeSigilEnforcementError(ValueError):
    pass


_CONTAINMENT_OBLIGATIONS = frozenset(
    {
        "derive-minimum-safe-containment",
        "fence-stale-writers",
        "commit-or-abort-recovery",
        "prove-exactly-once-effect-lineage",
        "bind-recovery-commit-to-attested-effect",
        "abort-on-evidence-conflict",
        "prove-recovery-authority-is-non-escalating",
        "seal-whole-universe-conservation-proof",
    }
)


@dataclass(frozen=True, slots=True)
class PrivilegedEffectIntent:
    effect_id: str
    subject: str
    operation: str
    request_digest: str

    def __post_init__(self) -> None:
        if not self.effect_id:
            raise NativeSigilEnforcementError("effect intent requires effect_id")
        if not self.subject:
            raise NativeSigilEnforcementError("effect intent requires subject")
        if not self.operation:
            raise NativeSigilEnforcementError("effect intent requires operation")
        if not self.request_digest:
            raise NativeSigilEnforcementError("effect intent requires request digest")


@dataclass(frozen=True, slots=True)
class EnforcementDecision:
    decision: str
    effect_id: str
    native_mir_fingerprint: str
    proof_digest: str
    failed_obligations: tuple[str, ...]
    digest: str

    def assert_sealed(self) -> None:
        expected = _decision_digest(
            self.decision,
            self.effect_id,
            self.native_mir_fingerprint,
            self.proof_digest,
            self.failed_obligations,
        )
        if self.digest != expected:
            raise NativeSigilEnforcementError("enforcement decision seal mismatch")


def _decision_digest(
    decision: str,
    effect_id: str,
    mir_fingerprint: str,
    proof_digest: str,
    failed_obligations: tuple[str, ...],
) -> str:
    payload = "\n".join(
        (
            f"decision={decision}",
            f"effect={effect_id}",
            f"mir={mir_fingerprint}",
            f"proof={proof_digest}",
            "failed=" + ",".join(failed_obligations),
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def evaluate_enforcement(
    mir: NativeSigilMir,
    proof: NativeSigilProofBundle,
    intent: PrivilegedEffectIntent,
) -> EnforcementDecision:
    """Verify the complete compiler->Library->proof chain and decide the boundary."""

    plan = require_native_sigil_proof(mir, proof)
    plan.assert_sealed()

    failed = tuple(
        receipt.obligation
        for receipt in proof.library_proof.receipts
        if not receipt.success
    )

    if proof.decision == "ALLOW":
        if failed:
            raise NativeSigilEnforcementError(
                "ALLOW proof contains failed Library obligations"
            )
        decision = "ALLOW"
    else:
        if not failed:
            raise NativeSigilEnforcementError(
                "non-ALLOW proof does not identify a failed Library obligation"
            )
        decision = (
            "CONTAIN"
            if any(item in _CONTAINMENT_OBLIGATIONS for item in failed)
            else "DENY"
        )

    result = EnforcementDecision(
        decision=decision,
        effect_id=intent.effect_id,
        native_mir_fingerprint=mir.fingerprint,
        proof_digest=proof.digest,
        failed_obligations=failed,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _decision_digest(
            result.decision,
            result.effect_id,
            result.native_mir_fingerprint,
            result.proof_digest,
            result.failed_obligations,
        ),
    )
    result.assert_sealed()
    return result


def enforce_effect(
    mir: NativeSigilMir,
    proof: NativeSigilProofBundle,
    intent: PrivilegedEffectIntent,
    effect: Callable[[PrivilegedEffectIntent], _T],
) -> tuple[EnforcementDecision, _T | None]:
    """Execute the privileged callback only when the sealed decision is ALLOW."""

    decision = evaluate_enforcement(mir, proof, intent)
    if decision.decision != "ALLOW":
        return decision, None
    return decision, effect(intent)
