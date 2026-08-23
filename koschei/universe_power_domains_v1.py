from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib


class PowerDomain(str, Enum):
    """Six real-world power domains inside the Koschei Universe.

    A grant in one domain is never authority in another domain.
    """

    IDENTITY = "identity"
    AUTHORITY = "authority"
    DATA = "data"
    COMPUTE = "compute"
    NETWORK = "network"
    CONTINUITY = "continuity"


@dataclass(frozen=True, slots=True)
class PowerGrant:
    subject: str
    domain: PowerDomain
    scope: str
    epoch: int
    actions: frozenset[str]
    grant_id: str

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("subject must be non-empty")
        if not self.scope.strip():
            raise ValueError("scope must be non-empty")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")
        if not self.actions or any(not action.strip() for action in self.actions):
            raise ValueError("actions must contain non-empty values")
        if not self.grant_id.strip():
            raise ValueError("grant_id must be non-empty")


@dataclass(frozen=True, slots=True)
class CrossDomainPermit:
    """Explicit, exact edge between two otherwise disconnected domains."""

    subject: str
    source_domain: PowerDomain
    target_domain: PowerDomain
    source_grant_id: str
    action: str
    scope: str
    epoch: int
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.source_domain is self.target_domain:
            raise ValueError("cross-domain permit requires distinct domains")
        if not self.subject.strip() or not self.source_grant_id.strip():
            raise ValueError("subject and source_grant_id must be non-empty")
        if not self.action.strip() or not self.scope.strip():
            raise ValueError("action and scope must be non-empty")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")
        if len(self.evidence_digest) != 64:
            raise ValueError("evidence_digest must be a sha256 hex digest")
        try:
            bytes.fromhex(self.evidence_digest)
        except ValueError as exc:
            raise ValueError("evidence_digest must be hexadecimal") from exc


@dataclass(frozen=True, slots=True)
class PowerDecision:
    allowed: bool
    reason: str


class UniversePowerGate:
    """Fail-closed six-domain authority gate.

    Design law: compromise(domain A) must not synthesize authority(domain B).
    Cross-domain edges do not exist unless an exact permit creates one for a
    single subject/action/scope/epoch/source-grant tuple.
    """

    @staticmethod
    def evidence_digest(*parts: str) -> str:
        if not parts or any(not part for part in parts):
            raise ValueError("evidence parts must be non-empty")
        payload = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def authorize(
        self,
        *,
        grant: PowerGrant,
        target_domain: PowerDomain,
        action: str,
        scope: str,
        epoch: int,
        permit: CrossDomainPermit | None = None,
    ) -> PowerDecision:
        if epoch != grant.epoch:
            return PowerDecision(False, "epoch-mismatch")
        if scope != grant.scope:
            return PowerDecision(False, "scope-mismatch")
        if action not in grant.actions:
            return PowerDecision(False, "action-not-granted")

        if target_domain is grant.domain:
            return PowerDecision(True, "same-domain-exact-grant")

        if permit is None:
            return PowerDecision(False, "cross-domain-edge-absent")
        if permit.subject != grant.subject:
            return PowerDecision(False, "permit-subject-mismatch")
        if permit.source_domain is not grant.domain:
            return PowerDecision(False, "permit-source-domain-mismatch")
        if permit.target_domain is not target_domain:
            return PowerDecision(False, "permit-target-domain-mismatch")
        if permit.source_grant_id != grant.grant_id:
            return PowerDecision(False, "permit-source-grant-mismatch")
        if permit.action != action:
            return PowerDecision(False, "permit-action-mismatch")
        if permit.scope != scope:
            return PowerDecision(False, "permit-scope-mismatch")
        if permit.epoch != epoch:
            return PowerDecision(False, "permit-epoch-mismatch")

        return PowerDecision(True, "explicit-cross-domain-permit")
