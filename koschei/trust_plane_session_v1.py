"""Trusted broker gateway for canonical Koschei command authority.

This layer is additive. It does not replace existing CLI/runtime machinery and it
does not implement a production secret store. A trusted host injects one broker
implementation plus a pinned broker policy. The broker resolves opaque target
identity to a CanonicalAuthoritySessionV1 entirely outside project bytes, argv,
environment variables, filenames and parser state.

The gateway deliberately keeps the issued authority session local to one command
call. Callers receive only the secret-free canonical command result.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from .canonical_authority_admission_v1 import CanonicalAuthoritySessionV1
from .canonical_command_authority_v1 import (
    CanonicalCommandResultV1,
    execute_canonical_command_v1,
)


_BROKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TARGET_BYTES = 32


class TrustPlaneSessionError(ValueError):
    """Raised when broker admission or command leasing fails closed."""


@dataclass(frozen=True, slots=True)
class TrustedBrokerPolicyV1:
    """Host-pinned identity for the authority broker allowed in this reality."""

    expected_broker_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.expected_broker_id, str)
            or _BROKER_ID_RE.fullmatch(self.expected_broker_id) is None
        ):
            raise TrustPlaneSessionError("invalid trusted broker policy")


@dataclass(frozen=True, slots=True)
class CanonicalAuthorityTargetV1:
    """Opaque host-selected target identity; never inferred from project content."""

    identity: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, bytes)
            or len(self.identity) != _TARGET_BYTES
            or not any(self.identity)
        ):
            raise TrustPlaneSessionError("canonical authority target must be 32 non-zero bytes")

    def __repr__(self) -> str:
        return "CanonicalAuthorityTargetV1(identity=<opaque>)"


@runtime_checkable
class CanonicalAuthorityBrokerV1(Protocol):
    """External trust-plane broker contract.

    Implementations own provider selection, secret custody, target registry and
    any durable rollback/high-water state. This module intentionally does not.
    """

    @property
    def broker_id(self) -> str: ...

    def issue_session(
        self,
        *,
        target: CanonicalAuthorityTargetV1,
        command: str,
        now: float | int | None = None,
    ) -> CanonicalAuthoritySessionV1: ...


def execute_with_trusted_broker_v1(
    command: str,
    path: str | Path,
    *,
    target: CanonicalAuthorityTargetV1,
    broker: CanonicalAuthorityBrokerV1,
    policy: TrustedBrokerPolicyV1,
    now: float | int | None = None,
) -> CanonicalCommandResultV1:
    """Lease one canonical authority session and consume it inside one command.

    Broker identity is pinned by host policy before any session request. Only
    canonical ``check``/``run`` purposes are admitted. Broker exceptions and
    malformed sessions are redacted at this boundary; there is no fallback.
    """

    if command not in ("check", "run"):
        raise TrustPlaneSessionError("trust-plane command is outside canonical scope")
    if not isinstance(target, CanonicalAuthorityTargetV1):
        raise TrustPlaneSessionError("opaque canonical authority target is required")
    if not isinstance(policy, TrustedBrokerPolicyV1):
        raise TrustPlaneSessionError("trusted broker policy is required")
    if not isinstance(broker, CanonicalAuthorityBrokerV1):
        raise TrustPlaneSessionError("canonical authority broker contract is required")
    try:
        broker_id = broker.broker_id
    except Exception:
        raise TrustPlaneSessionError("trusted broker identity admission failed") from None
    if broker_id != policy.expected_broker_id:
        raise TrustPlaneSessionError("trusted broker identity mismatch")

    try:
        authority = broker.issue_session(target=target, command=command, now=now)
    except Exception:
        raise TrustPlaneSessionError("trusted broker session issuance failed") from None
    if not isinstance(authority, CanonicalAuthoritySessionV1):
        raise TrustPlaneSessionError("trusted broker returned invalid canonical authority")

    try:
        return execute_canonical_command_v1(
            command,
            path,
            authority=authority,
            now=now,
        )
    except Exception as error:
        # Preserve the canonical command class only as a redacted trust-plane
        # failure. Broker/session internals must not escape through host logs.
        raise TrustPlaneSessionError("trusted broker canonical command failed") from None
