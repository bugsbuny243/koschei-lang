"""Authority-injected command adapter for Koschei-native check/run.

This is an additive bridge above existing CLI/runtime machinery.  It does not
replace compatibility commands and it never discovers authority from argv,
environment variables, filenames or project bytes.  A trusted host injects an
already-validated CanonicalAuthoritySessionV1 object directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .canonical_authority_admission_v1 import (
    CanonicalAuthoritySessionV1,
    check_with_canonical_authority_v1,
    run_with_canonical_authority_v1,
)
from .native_value_domains_v1 import NativeValue


class CanonicalCommandAuthorityError(ValueError):
    """Raised when a native command request is outside the sealed command surface."""


@dataclass(frozen=True, slots=True)
class CanonicalCommandResultV1:
    """Secret-free result envelope for a canonical native command."""

    command: Literal["check", "run"]
    project_id: bytes
    epoch: int
    value: NativeValue | None = None

    def __repr__(self) -> str:
        value_text = "<native-value>" if self.value is not None else "<none>"
        return (
            "CanonicalCommandResultV1("
            f"command={self.command!r}, epoch={self.epoch}, "
            f"project=<authenticated>, value={value_text})"
        )


def execute_canonical_command_v1(
    command: str,
    path: str | Path,
    *,
    authority: CanonicalAuthoritySessionV1,
    now: float | int | None = None,
) -> CanonicalCommandResultV1:
    """Execute one explicitly selected Koschei-native command.

    Only ``check`` and ``run`` are admitted in v1.  Unknown commands fail closed;
    there is no compatibility dispatch, source sniffing, parser probing or
    automatic command reinterpretation.
    """

    if command not in ("check", "run"):
        raise CanonicalCommandAuthorityError(
            "canonical native command must be explicitly 'check' or 'run'"
        )
    if not isinstance(authority, CanonicalAuthoritySessionV1):
        raise CanonicalCommandAuthorityError(
            "canonical native command requires injected authority"
        )

    if command == "check":
        checked = check_with_canonical_authority_v1(
            path,
            authority=authority,
            now=now,
        )
        return CanonicalCommandResultV1(
            command="check",
            project_id=checked.project_id,
            epoch=checked.epoch,
        )

    executed = run_with_canonical_authority_v1(
        path,
        authority=authority,
        now=now,
    )
    return CanonicalCommandResultV1(
        command="run",
        project_id=executed.project_id,
        epoch=executed.epoch,
        value=executed.value,
    )
