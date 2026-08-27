"""Authenticated canonical authorization decisions for Koschei Lang v1.

A decision is the bridge between canonical Koschei authority/policy evaluation and
later execution-permit minting. External evidence does not authorize an operation.
The trusted canonical authority layer must first produce an authenticated decision
bound to the exact evidence, subject, operation, request and epoch.

This Python module is a bootstrap contract. Native integration must ensure only the
canonical authority/policy engine can hold the decision key or invoke the issuer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import string

from .external_adapter_contract_v1 import ExternalAdapterEvidenceV1, ExternalAdapterGrantV1

_CTX = b"koschei.authorization-decision/v1\x00"
_HEX = frozenset(string.hexdigits.lower())
_OUTCOMES = frozenset({"allow", "deny", "contain"})


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


def issue_authorization_decision_v1(grant: ExternalAdapterGrantV1,
                                    evidence: ExternalAdapterEvidenceV1, *,
                                    decision_key: bytes, operation: str,
                                    request_digest: str, authority_basis_digest: str,
                                    policy_digest: str, outcome: str) -> AuthorizationDecisionV1:
    """Trusted bootstrap issuer; native runtime must restrict this to canonical authority evaluation."""
    key = _key(decision_key)
    grant.assert_sealed()
    evidence.assert_sealed(grant)
    operation = _text(operation, "operation")
    request = _digest(request_digest, "request_digest")
    authority_basis = _digest(authority_basis_digest, "authority_basis_digest")
    policy = _digest(policy_digest, "policy_digest")
    outcome = _text(outcome, "outcome")
    if outcome not in _OUTCOMES:
        raise AuthorizationDecisionV1Error("unknown authorization decision outcome")
    epoch = _epoch(evidence.observed_epoch, "observed_epoch")
    result = AuthorizationDecisionV1(
        evidence.evidence_digest, grant.provider_id, grant.consumer_id,
        grant.subject_scope_digest, operation, request, epoch,
        authority_basis, policy, outcome, "",
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
