"""Bounded host ingress capability for Koschei-native commands.

A trusted host constructs this capability after resolving its own configuration.
Untrusted command callers do not supply broker identity, target identity, provider
selection, temporal secrets or project identity. They may request only a purpose
that the capability was sealed to admit.

This remains additive above the existing compatibility CLI. It is the host-side
bridge needed before public command migration can safely occur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet

from .canonical_command_authority_v1 import CanonicalCommandResultV1
from .trust_plane_session_v1 import (
    CanonicalAuthorityBrokerV1,
    CanonicalAuthorityTargetV1,
    TrustedBrokerPolicyV1,
    execute_with_trusted_broker_v1,
)


class CanonicalHostIngressError(ValueError):
    """Raised when a caller exceeds the sealed host command capability."""


_ALLOWED_COMMANDS = frozenset(("check", "run"))


@dataclass(frozen=True, slots=True)
class CanonicalHostIngressV1:
    """Host-created command capability with hidden trust-plane bindings."""

    target: CanonicalAuthorityTargetV1 = field(repr=False)
    broker: CanonicalAuthorityBrokerV1 = field(repr=False)
    policy: TrustedBrokerPolicyV1 = field(repr=False)
    allowed_commands: FrozenSet[str] = field(default_factory=lambda: _ALLOWED_COMMANDS)

    def __post_init__(self) -> None:
        if not isinstance(self.target, CanonicalAuthorityTargetV1):
            raise CanonicalHostIngressError("canonical host ingress target is required")
        if not isinstance(self.policy, TrustedBrokerPolicyV1):
            raise CanonicalHostIngressError("canonical host ingress broker policy is required")
        if not isinstance(self.allowed_commands, frozenset):
            raise CanonicalHostIngressError("canonical host ingress command set must be frozen")
        if not self.allowed_commands or not self.allowed_commands.issubset(_ALLOWED_COMMANDS):
            raise CanonicalHostIngressError("canonical host ingress command scope is invalid")

    def __repr__(self) -> str:
        commands = ",".join(sorted(self.allowed_commands))
        return (
            "CanonicalHostIngressV1("
            f"commands={commands!r}, target=<opaque>, broker=<pinned>)"
        )

    def execute(
        self,
        command: str,
        path: str | Path,
        *,
        now: float | int | None = None,
    ) -> CanonicalCommandResultV1:
        """Execute one purpose already sealed into this ingress capability."""

        if command not in self.allowed_commands:
            raise CanonicalHostIngressError("command is outside host ingress authority")
        try:
            return execute_with_trusted_broker_v1(
                command,
                path,
                target=self.target,
                broker=self.broker,
                policy=self.policy,
                now=now,
            )
        except Exception:
            raise CanonicalHostIngressError("canonical host ingress execution failed") from None


def bind_host_ingress_v1(
    *,
    target: CanonicalAuthorityTargetV1,
    broker: CanonicalAuthorityBrokerV1,
    policy: TrustedBrokerPolicyV1,
    allow_check: bool = True,
    allow_run: bool = False,
) -> CanonicalHostIngressV1:
    """Seal a least-privilege host ingress capability.

    Run is opt-in. A check-only host therefore cannot be confused into execution
    merely because the underlying broker could issue run authority.
    """

    if not isinstance(allow_check, bool) or not isinstance(allow_run, bool):
        raise CanonicalHostIngressError("host ingress command flags must be boolean")
    commands = frozenset(
        command
        for command, enabled in (("check", allow_check), ("run", allow_run))
        if enabled
    )
    return CanonicalHostIngressV1(
        target=target,
        broker=broker,
        policy=policy,
        allowed_commands=commands,
    )
