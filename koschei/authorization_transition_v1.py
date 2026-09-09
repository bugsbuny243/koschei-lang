"""Provider-independent time-evolving authorization state for Koschei Lang v1.

This module is additive.  It does not replace the existing native authority,
AuthorizationDecisionV1, ExecutionPermitV1, broker, or OS-confinement gates.
It models the authority snapshot that must be true *at execution time*.

Intent is context, not authority.  Delegation verification is supplied by a
provider adapter, but stale/unknown/revoked verification fails closed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import string
from typing import Final

_HEX: Final = frozenset(string.hexdigits.lower())
_STATUSES: Final = frozenset({"active", "suspended", "revoked", "expired"})
_TRANSITIONS: Final = frozenset({"NARROW", "STEP_UP", "SUSPEND", "REVOKE", "EXPIRE"})
_REVOCATION_STATES: Final = frozenset({"valid", "revoked", "unknown"})


class AuthorizationTransitionV1Error(ValueError):
    """Raised when an authorization/delegation invariant is violated."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationTransitionV1Error(f"{label} cannot be empty")
    return value.strip()


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise AuthorizationTransitionV1Error(f"{label} must be a 64-character digest")
    lowered = value.lower()
    if any(ch not in _HEX for ch in lowered) or lowered == "0" * 64:
        raise AuthorizationTransitionV1Error(f"{label} must be a non-zero hexadecimal digest")
    return lowered


def _epoch(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AuthorizationTransitionV1Error(f"{label} must be a non-negative integer")
    return value


def _canonical_strings(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise AuthorizationTransitionV1Error(f"{label} must be a non-empty tuple")
    normalized = tuple(sorted({_text(value, label) for value in values}))
    if len(normalized) != len(values):
        raise AuthorizationTransitionV1Error(f"{label} must not contain duplicates")
    return normalized


def _hash(tag: bytes, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(tag + b"\x00" + encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ConstraintSetV1:
    """Canonical provider-independent attenuation lattice.

    Empty/wildcard sets are deliberately not part of v1; callers must state the
    exact allowed resource, operation, argument class and audience.
    """

    resources: tuple[str, ...]
    operations: tuple[str, ...]
    arguments: tuple[str, ...]
    audience: tuple[str, ...]
    magnitude_max: int | None
    valid_from_epoch: int
    expires_before_epoch: int | None
    delegation_depth: int
    redelegation: bool

    def __post_init__(self) -> None:
        for field in ("resources", "operations", "arguments", "audience"):
            object.__setattr__(self, field, _canonical_strings(getattr(self, field), field))
        if self.magnitude_max is not None:
            if not isinstance(self.magnitude_max, int) or isinstance(self.magnitude_max, bool) or self.magnitude_max < 0:
                raise AuthorizationTransitionV1Error("magnitude_max must be a non-negative integer or None")
        _epoch(self.valid_from_epoch, "valid_from_epoch")
        if self.expires_before_epoch is not None:
            _epoch(self.expires_before_epoch, "expires_before_epoch")
            if self.expires_before_epoch <= self.valid_from_epoch:
                raise AuthorizationTransitionV1Error("expires_before_epoch must be after valid_from_epoch")
        if not isinstance(self.delegation_depth, int) or isinstance(self.delegation_depth, bool) or self.delegation_depth < 0:
            raise AuthorizationTransitionV1Error("delegation_depth must be a non-negative integer")
        if not isinstance(self.redelegation, bool):
            raise AuthorizationTransitionV1Error("redelegation must be boolean")

    @property
    def digest(self) -> str:
        return _hash(b"koschei.constraint-set/v1", asdict(self))

    def assert_live(self, epoch: int) -> None:
        now = _epoch(epoch, "epoch")
        if now < self.valid_from_epoch:
            raise AuthorizationTransitionV1Error("constraint set is not live yet")
        if self.expires_before_epoch is not None and now >= self.expires_before_epoch:
            raise AuthorizationTransitionV1Error("constraint set has expired")

    def assert_attenuates(self, parent: "ConstraintSetV1", *, delegation_hop: bool = False) -> None:
        for field in ("resources", "operations", "arguments", "audience"):
            child_values = set(getattr(self, field))
            parent_values = set(getattr(parent, field))
            if not child_values.issubset(parent_values):
                raise AuthorizationTransitionV1Error(f"{field} broadens parent authority")
        if parent.magnitude_max is not None:
            if self.magnitude_max is None or self.magnitude_max > parent.magnitude_max:
                raise AuthorizationTransitionV1Error("magnitude broadens parent authority")
        if self.valid_from_epoch < parent.valid_from_epoch:
            raise AuthorizationTransitionV1Error("validity start broadens parent authority")
        if parent.expires_before_epoch is not None:
            if self.expires_before_epoch is None or self.expires_before_epoch > parent.expires_before_epoch:
                raise AuthorizationTransitionV1Error("validity end broadens parent authority")
        if self.delegation_depth > parent.delegation_depth:
            raise AuthorizationTransitionV1Error("delegation_depth broadens parent authority")
        if self.redelegation and not parent.redelegation:
            raise AuthorizationTransitionV1Error("redelegation broadens parent authority")
        if delegation_hop:
            if not parent.redelegation or parent.delegation_depth == 0:
                raise AuthorizationTransitionV1Error("parent does not permit another delegation hop")
            if self.delegation_depth >= parent.delegation_depth:
                raise AuthorizationTransitionV1Error("delegation hop must consume delegation depth")


@dataclass(frozen=True, slots=True)
class IntentCommitmentV1:
    """Purpose binding only.  This object never grants execution authority."""

    principal: str
    intent_digest: str
    purpose_digest: str
    created_epoch: int
    authority: bool = False
    version: int = 1

    def __post_init__(self) -> None:
        _text(self.principal, "principal")
        _digest(self.intent_digest, "intent_digest")
        _digest(self.purpose_digest, "purpose_digest")
        _epoch(self.created_epoch, "created_epoch")
        if self.authority:
            raise AuthorizationTransitionV1Error("intent commitment cannot carry authority")

    @property
    def digest(self) -> str:
        return _hash(b"koschei.intent-commitment/v1", asdict(self))


@dataclass(frozen=True, slots=True)
class DelegationLinkV1:
    """One adapter-verified delegation link plus its current validity check."""

    delegation_id: str
    parent_delegation_id: str | None
    issuer: str
    subject: str
    constraints: ConstraintSetV1
    parent_commitment: str | None
    checked_epoch: int
    signature_valid: bool
    revocation_status: str
    version: int = 1

    def __post_init__(self) -> None:
        _text(self.delegation_id, "delegation_id")
        if self.parent_delegation_id is not None:
            _text(self.parent_delegation_id, "parent_delegation_id")
        _text(self.issuer, "issuer")
        _text(self.subject, "subject")
        if self.parent_commitment is not None:
            _digest(self.parent_commitment, "parent_commitment")
        _epoch(self.checked_epoch, "checked_epoch")
        if not isinstance(self.signature_valid, bool):
            raise AuthorizationTransitionV1Error("signature_valid must be boolean")
        if self.revocation_status not in _REVOCATION_STATES:
            raise AuthorizationTransitionV1Error("unknown revocation_status")

    @property
    def authority_digest(self) -> str:
        payload = {
            "delegation_id": self.delegation_id,
            "parent_delegation_id": self.parent_delegation_id,
            "issuer": self.issuer,
            "subject": self.subject,
            "constraints_digest": self.constraints.digest,
            "parent_commitment": self.parent_commitment,
            "version": self.version,
        }
        return _hash(b"koschei.delegation-authority/v1", payload)

    @property
    def verification_digest(self) -> str:
        payload = {
            "authority_digest": self.authority_digest,
            "checked_epoch": self.checked_epoch,
            "signature_valid": self.signature_valid,
            "revocation_status": self.revocation_status,
        }
        return _hash(b"koschei.delegation-verification/v1", payload)

    def assert_current(self, epoch: int) -> None:
        now = _epoch(epoch, "epoch")
        if self.checked_epoch != now:
            raise AuthorizationTransitionV1Error("delegation validity is stale for execution epoch")
        if not self.signature_valid:
            raise AuthorizationTransitionV1Error("delegation signature is not currently valid")
        if self.revocation_status != "valid":
            raise AuthorizationTransitionV1Error("delegation revocation state is not currently valid")
        self.constraints.assert_live(now)


def delegation_chain_authority_digest_v1(chain: tuple[DelegationLinkV1, ...]) -> str:
    if not isinstance(chain, tuple) or not chain:
        raise AuthorizationTransitionV1Error("delegation chain cannot be empty")
    return _hash(
        b"koschei.delegation-chain-authority/v1",
        [link.authority_digest for link in chain],
    )


def assert_delegation_chain_current_v1(
    chain: tuple[DelegationLinkV1, ...], *, execution_epoch: int
) -> str:
    """Verify the whole chain now; historical validity is intentionally insufficient."""
    now = _epoch(execution_epoch, "execution_epoch")
    if not isinstance(chain, tuple) or not chain:
        raise AuthorizationTransitionV1Error("delegation chain cannot be empty")
    for index, link in enumerate(chain):
        link.assert_current(now)
        if index == 0:
            if link.parent_delegation_id is not None or link.parent_commitment is not None:
                raise AuthorizationTransitionV1Error("root delegation cannot name a parent")
            continue
        parent = chain[index - 1]
        # VALID_CHILD_DELEGATION requires VALID_PARENT_NOW.
        parent.assert_current(now)
        if link.parent_delegation_id != parent.delegation_id:
            raise AuthorizationTransitionV1Error("delegation parent id mismatch")
        if link.parent_commitment != parent.authority_digest:
            raise AuthorizationTransitionV1Error("delegation parent commitment mismatch")
        if link.issuer != parent.subject:
            raise AuthorizationTransitionV1Error("delegation issuer is not the parent subject")
        link.constraints.assert_attenuates(parent.constraints, delegation_hop=True)
    return _hash(
        b"koschei.delegation-chain-current/v1",
        [link.verification_digest for link in chain],
    )


@dataclass(frozen=True, slots=True)
class AuthorizationStateV1:
    subject: str
    intent_commitment_digest: str
    delegation_chain_authority_digest: str
    authority_ceiling: ConstraintSetV1
    effective_constraints: ConstraintSetV1
    status: str
    epoch: int
    previous_state_digest: str | None
    state_digest: str
    authority: bool = False
    version: int = 1

    def __post_init__(self) -> None:
        _text(self.subject, "subject")
        _digest(self.intent_commitment_digest, "intent_commitment_digest")
        _digest(self.delegation_chain_authority_digest, "delegation_chain_authority_digest")
        if self.status not in _STATUSES:
            raise AuthorizationTransitionV1Error("unknown authorization status")
        _epoch(self.epoch, "epoch")
        if self.previous_state_digest is not None:
            _digest(self.previous_state_digest, "previous_state_digest")
        if self.state_digest:
            _digest(self.state_digest, "state_digest")
        if self.authority:
            raise AuthorizationTransitionV1Error("authorization state receipt cannot carry ambient authority")
        self.effective_constraints.assert_attenuates(self.authority_ceiling)

    def assert_active(self, epoch: int) -> None:
        now = _epoch(epoch, "epoch")
        if self.status != "active":
            raise AuthorizationTransitionV1Error("authorization state is not active")
        if now < self.epoch:
            raise AuthorizationTransitionV1Error("authorization state is from the future")
        self.effective_constraints.assert_live(now)


def _state_digest(state: AuthorizationStateV1) -> str:
    payload = {
        "subject": state.subject,
        "intent_commitment_digest": state.intent_commitment_digest,
        "delegation_chain_authority_digest": state.delegation_chain_authority_digest,
        "authority_ceiling_digest": state.authority_ceiling.digest,
        "effective_constraints_digest": state.effective_constraints.digest,
        "status": state.status,
        "epoch": state.epoch,
        "previous_state_digest": state.previous_state_digest,
        "authority": state.authority,
        "version": state.version,
    }
    return _hash(b"koschei.authorization-state/v1", payload)


def issue_authorization_state_v1(
    intent: IntentCommitmentV1,
    chain: tuple[DelegationLinkV1, ...],
    *,
    epoch: int,
    effective_constraints: ConstraintSetV1 | None = None,
) -> AuthorizationStateV1:
    """Create the initial state only after current delegation verification."""
    now = _epoch(epoch, "epoch")
    assert_delegation_chain_current_v1(chain, execution_epoch=now)
    leaf = chain[-1]
    if intent.principal != leaf.subject:
        raise AuthorizationTransitionV1Error("intent principal does not match delegated subject")
    ceiling = leaf.constraints
    effective = effective_constraints or ceiling
    effective.assert_attenuates(ceiling)
    effective.assert_live(now)
    state = AuthorizationStateV1(
        subject=leaf.subject,
        intent_commitment_digest=intent.digest,
        delegation_chain_authority_digest=delegation_chain_authority_digest_v1(chain),
        authority_ceiling=ceiling,
        effective_constraints=effective,
        status="active",
        epoch=now,
        previous_state_digest=None,
        state_digest="",
    )
    return replace(state, state_digest=_state_digest(state))


@dataclass(frozen=True, slots=True)
class AuthorizationTransitionV1:
    kind: str
    epoch: int
    previous_state_digest: str
    next_state_digest: str
    reason_digest: str
    transition_digest: str
    version: int = 1


def transition_authorization_state_v1(
    current: AuthorizationStateV1,
    *,
    kind: str,
    epoch: int,
    reason_digest: str,
    next_effective_constraints: ConstraintSetV1 | None = None,
) -> tuple[AuthorizationStateV1, AuthorizationTransitionV1]:
    """Apply one explicit transition; authority never silently recovers."""
    if _state_digest(replace(current, state_digest="")) != current.state_digest:
        raise AuthorizationTransitionV1Error("authorization state seal mismatch")
    transition_kind = _text(kind, "kind").upper()
    if transition_kind not in _TRANSITIONS:
        raise AuthorizationTransitionV1Error("unknown authorization transition")
    now = _epoch(epoch, "epoch")
    if now <= current.epoch:
        raise AuthorizationTransitionV1Error("authorization transition epoch must increase")
    reason = _digest(reason_digest, "reason_digest")
    if current.status in {"revoked", "expired"}:
        raise AuthorizationTransitionV1Error("terminal authorization state cannot transition")
    if current.status == "suspended" and transition_kind not in {"REVOKE", "EXPIRE"}:
        raise AuthorizationTransitionV1Error("suspended authority cannot silently recover")

    effective = current.effective_constraints
    next_status = current.status
    if transition_kind == "NARROW":
        if next_effective_constraints is None:
            raise AuthorizationTransitionV1Error("NARROW requires next_effective_constraints")
        next_effective_constraints.assert_attenuates(current.effective_constraints)
        effective = next_effective_constraints
        next_status = "active"
    elif transition_kind == "STEP_UP":
        if next_effective_constraints is None:
            raise AuthorizationTransitionV1Error("STEP_UP requires next_effective_constraints")
        # Step-up may restore previously attenuated authority, but never exceed
        # the immutable outer authority ceiling.
        next_effective_constraints.assert_attenuates(current.authority_ceiling)
        effective = next_effective_constraints
        next_status = "active"
    else:
        if next_effective_constraints is not None:
            raise AuthorizationTransitionV1Error(f"{transition_kind} cannot change constraints")
        next_status = {
            "SUSPEND": "suspended",
            "REVOKE": "revoked",
            "EXPIRE": "expired",
        }[transition_kind]

    next_state = AuthorizationStateV1(
        subject=current.subject,
        intent_commitment_digest=current.intent_commitment_digest,
        delegation_chain_authority_digest=current.delegation_chain_authority_digest,
        authority_ceiling=current.authority_ceiling,
        effective_constraints=effective,
        status=next_status,
        epoch=now,
        previous_state_digest=current.state_digest,
        state_digest="",
    )
    next_state = replace(next_state, state_digest=_state_digest(next_state))
    transition_payload = {
        "kind": transition_kind,
        "epoch": now,
        "previous_state_digest": current.state_digest,
        "next_state_digest": next_state.state_digest,
        "reason_digest": reason,
        "version": 1,
    }
    transition_digest = _hash(b"koschei.authorization-transition/v1", transition_payload)
    transition = AuthorizationTransitionV1(
        kind=transition_kind,
        epoch=now,
        previous_state_digest=current.state_digest,
        next_state_digest=next_state.state_digest,
        reason_digest=reason,
        transition_digest=transition_digest,
    )
    return next_state, transition


@dataclass(frozen=True, slots=True)
class ExecutionAuthorizationSnapshotV1:
    state_digest: str
    intent_commitment_digest: str
    delegation_chain_authority_digest: str
    delegation_current_verification_digest: str
    effective_constraints_digest: str
    execution_epoch: int
    snapshot_digest: str
    authority: bool = False
    version: int = 1


def authorization_snapshot_for_execution_v1(
    state: AuthorizationStateV1,
    chain: tuple[DelegationLinkV1, ...],
    *,
    execution_epoch: int,
) -> ExecutionAuthorizationSnapshotV1:
    """Revalidate current parent/delegation state and seal an execution-time snapshot."""
    now = _epoch(execution_epoch, "execution_epoch")
    if _state_digest(replace(state, state_digest="")) != state.state_digest:
        raise AuthorizationTransitionV1Error("authorization state seal mismatch")
    state.assert_active(now)
    current_verification = assert_delegation_chain_current_v1(chain, execution_epoch=now)
    authority_digest = delegation_chain_authority_digest_v1(chain)
    if authority_digest != state.delegation_chain_authority_digest:
        raise AuthorizationTransitionV1Error("current delegation chain differs from authorization state")
    leaf = chain[-1]
    if leaf.subject != state.subject:
        raise AuthorizationTransitionV1Error("current delegation subject differs from authorization state")
    state.effective_constraints.assert_attenuates(leaf.constraints)
    payload = {
        "state_digest": state.state_digest,
        "intent_commitment_digest": state.intent_commitment_digest,
        "delegation_chain_authority_digest": authority_digest,
        "delegation_current_verification_digest": current_verification,
        "effective_constraints_digest": state.effective_constraints.digest,
        "execution_epoch": now,
        "authority": False,
        "version": 1,
    }
    digest = _hash(b"koschei.execution-authorization-snapshot/v1", payload)
    return ExecutionAuthorizationSnapshotV1(
        state_digest=state.state_digest,
        intent_commitment_digest=state.intent_commitment_digest,
        delegation_chain_authority_digest=authority_digest,
        delegation_current_verification_digest=current_verification,
        effective_constraints_digest=state.effective_constraints.digest,
        execution_epoch=now,
        snapshot_digest=digest,
    )
