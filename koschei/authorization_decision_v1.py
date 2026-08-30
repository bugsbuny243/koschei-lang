"""Authenticated authorization decisions derived from canonical Koschei authority v1.

External evidence is not authority.  Decision content is no longer caller-selected:
the trusted issuer verifies a CanonicalAuthorityBasisV1 produced by the existing
native MIR -> request -> proof -> enforcement path and derives operation, exact
request, epoch, policy identity, authority basis, and outcome from that receipt.

The decision HMAC authenticates the derived bridge for later execution-permit
minting.  The decision key does not replace the native authority checks that must
succeed before issuance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import string

from .canonical_authority_basis_v1 import CanonicalAuthorityBasisV1
from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_proof_pipeline_v1 import NativeSigilProofBundle
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, RequestBoundProof

_CTX = b"koschei.authorization-decision/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
_OUTCOMES = frozenset({"allow", "deny", "contain"})
_NATIVE_OUTCOME_MAP = {"ALLOW": "allow", "DENY": "deny", "CONTAIN": "contain"}


class AuthorizationDecisionV1Error(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationDecisionV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise AuthorizationDecisionV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise AuthorizationDecisionV1Error(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AuthorizationDecisionV1Error(f"{label} must be a non-negative integer")
    return value


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise AuthorizationDecisionV1Error("decision_key must contain at least 32 bytes")
    return value


def _payload(*, evidence_digest: str, provider_id: str, consumer_id: str,
             subject_scope_digest: str, operation: str, request_digest: str,
             epoch: int, authority_basis_digest: str, policy_digest: str,
             outcome: str) -> bytes:
    rows = (
        f"evidence={evidence_digest}", f"provider={provider_id}",
        f"consumer={consumer_id}", f"subject={subject_scope_digest}",
        f"operation={operation}", f"request={request_digest}", f"epoch={epoch}",
        f"authority_basis={authority_basis_digest}", f"policy={policy_digest}",
        f"outcome={outcome}",
    )
    return _CTX + "\n".join(rows).encode("utf-8")


@dataclass(frozen=True, slots=True)
class AuthorizationDecisionV1:
    evidence_digest: str
    provider_id: str
    consumer_id: str
    subject_scope_digest: str
    operation: str
    request_digest: str
    decision_epoch: int
    authority_basis_digest: str
    policy_digest: str
    outcome: str
    decision_digest: str
    version: int = 1

    def assert_authenticated(self, *, decision_key: bytes,
                             grant: ExternalAdapterGrantV1,
                             evidence: ExternalAdapterEvidenceV1) -> None:
        key = _key(decision_key)
        grant.assert_sealed()
        evidence.assert_sealed(grant)
        evidence_digest = _digest(self.evidence_digest, "evidence_digest")
        if evidence_digest != evidence.evidence_digest:
            raise AuthorizationDecisionV1Error("authorization decision belongs to different evidence")
        provider = _text(self.provider_id, "provider_id")
        consumer = _text(self.consumer_id, "consumer_id")
        if provider != grant.provider_id or consumer != grant.consumer_id:
            raise AuthorizationDecisionV1Error("authorization decision provider/consumer mismatch")
        subject = _digest(self.subject_scope_digest, "subject_scope_digest")
        if subject != grant.subject_scope_digest:
            raise AuthorizationDecisionV1Error("authorization decision subject mismatch")
        operation = _text(self.operation, "operation")
        request = _digest(self.request_digest, "request_digest")
        epoch = _epoch(self.decision_epoch, "decision_epoch")
        if epoch != evidence.observed_epoch:
            raise AuthorizationDecisionV1Error("authorization decision epoch must equal evidence observation epoch")
        authority_basis = _digest(self.authority_basis_digest, "authority_basis_digest")
        policy = _digest(self.policy_digest, "policy_digest")
        outcome = _text(self.outcome, "outcome")
        if outcome not in _OUTCOMES:
            raise AuthorizationDecisionV1Error("unknown authorization decision outcome")
        expected = hmac.new(key, _payload(
            evidence_digest=evidence_digest, provider_id=provider, consumer_id=consumer,
            subject_scope_digest=subject, operation=operation, request_digest=request,
            epoch=epoch, authority_basis_digest=authority_basis, policy_digest=policy,
            outcome=outcome,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(self.decision_digest, expected):
            raise AuthorizationDecisionV1Error("authorization decision authentication failed")

    def assert_allows(self) -> None:
        if self.outcome != "allow":
            raise AuthorizationDecisionV1Error("authorization decision does not allow execution")


def issue_authorization_decision_v1(
    grant: ExternalAdapterGrantV1,
    evidence: ExternalAdapterEvidenceV1,
    basis: CanonicalAuthorityBasisV1,
    *,
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    proof: NativeSigilProofBundle,
    bound: RequestBoundProof,
    decision_key: bytes,
) -> AuthorizationDecisionV1:
    """Issue only from the verified native enforcement chain; no authority digest injection."""
    key = _key(decision_key)
    grant.assert_sealed()
    evidence.assert_sealed(grant)
    native_decision = basis.assert_sealed(mir=mir, request=request, proof=proof, bound=bound)
    if basis.subject_scope_digest != grant.subject_scope_digest:
        raise AuthorizationDecisionV1Error(
            "external grant subject scope does not match canonical authority basis"
        )
    if basis.epoch != evidence.observed_epoch:
        raise AuthorizationDecisionV1Error(
            "canonical authority epoch does not match external evidence epoch"
        )
    outcome = _NATIVE_OUTCOME_MAP.get(native_decision.decision)
    if outcome is None:
        raise AuthorizationDecisionV1Error("unknown native enforcement outcome")
    # The native MIR fingerprint is the executable policy/program identity for v1.
    policy = _digest(mir.fingerprint, "native_mir_fingerprint")
    result = AuthorizationDecisionV1(
        evidence_digest=evidence.evidence_digest,
        provider_id=grant.provider_id,
        consumer_id=grant.consumer_id,
        subject_scope_digest=basis.subject_scope_digest,
        operation=basis.operation,
        request_digest=basis.canonical_request_digest,
        decision_epoch=basis.epoch,
        authority_basis_digest=basis.basis_digest,
        policy_digest=policy,
        outcome=outcome,
        decision_digest="",
    )
    mac = hmac.new(key, _payload(
        evidence_digest=result.evidence_digest, provider_id=result.provider_id,
        consumer_id=result.consumer_id, subject_scope_digest=result.subject_scope_digest,
        operation=result.operation, request_digest=result.request_digest,
        epoch=result.decision_epoch, authority_basis_digest=result.authority_basis_digest,
        policy_digest=result.policy_digest, outcome=result.outcome,
    ), hashlib.sha256).hexdigest()
    object.__setattr__(result, "decision_digest", mac)
    result.assert_authenticated(decision_key=key, grant=grant, evidence=evidence)
    return result
