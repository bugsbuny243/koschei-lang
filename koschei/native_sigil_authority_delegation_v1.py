"""Epoch-bound non-escalating authority delegation for native Koschei v1.

Koschei must be able to govern humans, services, AI agents and future actors
without giving any of them ambient authority.  This module turns `vor` authority
into an explicit delegation chain.

A root grant is bound to one `vor` subject, one canonical actor identity, one
Universe/MIR identity, one epoch and an exact operation set.  A child grant may
only remove operations; it cannot widen, switch subjects, switch epochs or move
to another compiler/Universe identity.

This lets an operator delegate a narrow task to an agent, and that agent delegate
an even narrower task to a sub-agent, while preserving hash-bound parent links.
A self-hash does not authenticate an issuer: the surrounding enforcement path
must admit the root and verify the lineage.  It is actor-agnostic: "agent" is a
deployment role, not a new Koschei semantic root.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable

from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest

_CTX = b"koschei.native-sigil-authority-delegation/v1\x00"


class AuthorityDelegationError(ValueError):
    pass


def _canonical_operations(operations: Iterable[str]) -> tuple[str, ...]:
    if isinstance(operations, (str, bytes)):
        raise AuthorityDelegationError("authority operations must be an iterable of operation names")
    try:
        values = tuple(operations)
    except TypeError as exc:
        raise AuthorityDelegationError("authority operations must be iterable") from exc
    if not values:
        raise AuthorityDelegationError("authority grant requires non-empty operations")
    for value in values:
        _require_text(value, "operation")
        if "," in value:
            raise AuthorityDelegationError("authority operation cannot contain the v1 comma delimiter")
    return tuple(sorted(set(values)))


def _require_text(value: str, field: str) -> None:
    if type(value) is not str or not value:
        raise AuthorityDelegationError(f"authority grant {field} must be a non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AuthorityDelegationError(f"authority grant {field} cannot contain control characters")


def _require_nonnegative_integer(value: int, field: str) -> None:
    if type(value) is not int or value < 0:
        raise AuthorityDelegationError(f"authority grant {field} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    grant_id: str
    subject: str
    actor_identity_digest: str
    epoch: int
    operations: tuple[str, ...]
    native_mir_fingerprint: str
    universe_plan_digest: str
    parent_grant_digest: str
    depth: int
    digest: str
    version: int = 1

    def assert_sealed(self, mir: NativeSigilMir) -> None:
        mir.assert_sealed()
        if type(self.version) is not int or self.version != 1:
            raise AuthorityDelegationError("unsupported authority grant version")
        expected = _grant_digest(
            self.grant_id,
            self.subject,
            self.actor_identity_digest,
            self.epoch,
            self.operations,
            self.native_mir_fingerprint,
            self.universe_plan_digest,
            self.parent_grant_digest,
            self.depth,
        )
        if self.native_mir_fingerprint != mir.fingerprint:
            raise AuthorityDelegationError("authority grant MIR identity mismatch")
        if self.universe_plan_digest != mir.universe_plan_digest:
            raise AuthorityDelegationError("authority grant Universe identity mismatch")
        vor_subjects = {item.subject for item in mir.bindings if item.sigil == "vor"}
        if self.subject not in vor_subjects:
            raise AuthorityDelegationError(
                "authority grant subject is not declared by a vor binding"
            )
        if self.digest != expected:
            raise AuthorityDelegationError("authority grant seal mismatch")


def _grant_digest(
    grant_id: str,
    subject: str,
    actor_identity_digest: str,
    epoch: int,
    operations: tuple[str, ...],
    mir_fingerprint: str,
    universe_digest: str,
    parent_digest: str,
    depth: int,
) -> str:
    # Keep the existing v1 encoding and valid seals stable. Reject ambiguous
    # delimiters instead of silently changing the authority identity format.
    for field, value in (
        ("grant_id", grant_id),
        ("subject", subject),
        ("actor_identity_digest", actor_identity_digest),
        ("native_mir_fingerprint", mir_fingerprint),
        ("universe_plan_digest", universe_digest),
        ("parent_grant_digest", parent_digest),
    ):
        _require_text(value, field)
    _require_nonnegative_integer(epoch, "epoch")
    _require_nonnegative_integer(depth, "depth")
    if type(operations) is not tuple or operations != _canonical_operations(operations):
        raise AuthorityDelegationError("authority grant operations are not canonical")
    if depth == 0:
        if parent_digest != "ROOT":
            raise AuthorityDelegationError("root authority grant must use the ROOT parent marker")
    elif re.fullmatch(r"[a-f0-9]{64}", parent_digest) is None:
        raise AuthorityDelegationError("child authority grant requires a parent digest")
    values = (
        grant_id,
        subject,
        actor_identity_digest,
        str(epoch),
        ",".join(operations),
        mir_fingerprint,
        universe_digest,
        parent_digest,
        str(depth),
    )
    payload = "\n".join(values).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def issue_root_grant(
    mir: NativeSigilMir,
    *,
    grant_id: str,
    subject: str,
    actor_identity_digest: str,
    epoch: int,
    operations: Iterable[str],
) -> AuthorityGrant:
    """Issue explicit root authority for one canonical `vor` subject.

    This function does not discover policy or fabricate authority.  The caller is
    expected to invoke it only after the Library's `derive-least-authority`
    obligation has been satisfied by the surrounding proof/enforcement path.
    """
    mir.assert_sealed()
    canonical = _canonical_operations(operations)
    result = AuthorityGrant(
        grant_id=grant_id,
        subject=subject,
        actor_identity_digest=actor_identity_digest,
        epoch=epoch,
        operations=canonical,
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        parent_grant_digest="ROOT",
        depth=0,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _grant_digest(
            result.grant_id,
            result.subject,
            result.actor_identity_digest,
            result.epoch,
            result.operations,
            result.native_mir_fingerprint,
            result.universe_plan_digest,
            result.parent_grant_digest,
            result.depth,
        ),
    )
    result.assert_sealed(mir)
    return result


def delegate_grant(
    mir: NativeSigilMir,
    parent: AuthorityGrant,
    *,
    grant_id: str,
    actor_identity_digest: str,
    operations: Iterable[str],
) -> AuthorityGrant:
    """Create a child grant that can only narrow its parent's authority."""
    parent.assert_sealed(mir)
    canonical = _canonical_operations(operations)
    if not set(canonical).issubset(parent.operations):
        raise AuthorityDelegationError("delegated authority cannot widen parent operations")
    result = AuthorityGrant(
        grant_id=grant_id,
        subject=parent.subject,
        actor_identity_digest=actor_identity_digest,
        epoch=parent.epoch,
        operations=canonical,
        native_mir_fingerprint=parent.native_mir_fingerprint,
        universe_plan_digest=parent.universe_plan_digest,
        parent_grant_digest=parent.digest,
        depth=parent.depth + 1,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _grant_digest(
            result.grant_id,
            result.subject,
            result.actor_identity_digest,
            result.epoch,
            result.operations,
            result.native_mir_fingerprint,
            result.universe_plan_digest,
            result.parent_grant_digest,
            result.depth,
        ),
    )
    result.assert_sealed(mir)
    return result


def require_request_authority(
    mir: NativeSigilMir,
    request: CanonicalEffectRequest,
    grant: AuthorityGrant,
) -> None:
    """Check request coverage by a grant already admitted by enforcement.

    This does not authenticate a self-hashed grant or admit an unverified parent
    lineage. Root admission and ancestor validation remain caller obligations.
    """
    request.assert_sealed(mir)
    grant.assert_sealed(mir)
    if request.subject != grant.subject:
        raise AuthorityDelegationError("request subject is outside authority grant")
    if request.identity_digest != grant.actor_identity_digest:
        raise AuthorityDelegationError("request actor identity is outside authority grant")
    if request.epoch != grant.epoch:
        raise AuthorityDelegationError("request epoch is stale for authority grant")
    if request.operation not in grant.operations:
        raise AuthorityDelegationError("request operation is not delegated")
