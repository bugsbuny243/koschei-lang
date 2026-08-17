"""Machine-readable inventory for Koschei's canonical execution authority migration.

This module does not change execution behavior.  It makes the remaining
compatibility debt explicit and fail-closed so migration work cannot describe a
legacy path as Native IR by accident.

The target architecture is:

    authenticated Koschei frontend / Object Space -> Native IR -> sealed runtime

Public ``check``, ``run`` and ``build`` remain migration debt until their exact
entry paths stop depending on the compatibility ModuleGraph/MIR/AST authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


SCHEMA = "koschei.canonical-dispatch-inventory/v1"


class DispatchClass(str, Enum):
    """Allowed authority classifications for canonical execution entrypoints."""

    NATIVE_IR = "NATIVE_IR"
    COMPAT_MIGRATION_ONLY = "COMPAT_MIGRATION_ONLY"
    FAIL_CLOSED_UNMIGRATED = "FAIL_CLOSED_UNMIGRATED"


class DispatchInventoryError(ValueError):
    """Raised when an execution entrypoint has no explicit authority class."""


@dataclass(frozen=True, slots=True)
class DispatchInventoryEntryV1:
    command: str
    implementation_symbol: str
    classification: DispatchClass
    pipeline: tuple[str, ...]
    legacy_fallback: bool = False


# This is intentionally the exact public execution set for A1.  Inspection-only
# commands such as tokens/ast/mir/caps/emit-go are not execution authorities.
PUBLIC_CANONICAL_EXECUTION_COMMANDS = frozenset({"check", "run", "build"})


INVENTORY: tuple[DispatchInventoryEntryV1, ...] = (
    DispatchInventoryEntryV1(
        command="check",
        implementation_symbol="koschei.cli.command_check",
        classification=DispatchClass.COMPAT_MIGRATION_ONLY,
        pipeline=(
            "require_ks_extension",
            "load_graph",
            "check_graph",
            "require_mir",
        ),
    ),
    DispatchInventoryEntryV1(
        command="run",
        implementation_symbol="koschei.cli_entry._run_with_public_budget",
        classification=DispatchClass.COMPAT_MIGRATION_ONLY,
        pipeline=(
            "koschei.cli.open_graph",
            "check_graph",
            "require_mir",
            "run_mir_with_budget",
        ),
    ),
    DispatchInventoryEntryV1(
        command="build",
        implementation_symbol="koschei.cli_entry._build_with_public_lock",
        classification=DispatchClass.COMPAT_MIGRATION_ONLY,
        pipeline=(
            "require_ks_extension",
            "verified-module-lock-when-requested",
            "koschei.cli.open_graph",
            "check_graph",
            "require_mir",
            "mir_go_v1-or-ast_go_compat_v1",
        ),
        legacy_fallback=True,
    ),
)


# Existing authenticated Native IR authority that public execution should migrate
# toward.  It is deliberately not presented as a public CLI authority yet.
NATIVE_IR_MIGRATION_TARGET = (
    "koschei.object_space_native_ir_dispatch_v1."
    "execute_authenticated_object_space_native_ir_v1"
)


def inventory_by_command() -> dict[str, DispatchInventoryEntryV1]:
    return {entry.command: entry for entry in INVENTORY}


def require_public_dispatch_classification(command: str) -> DispatchInventoryEntryV1:
    """Return explicit authority metadata or fail closed for an unknown command."""

    entry = inventory_by_command().get(command)
    if entry is None:
        raise DispatchInventoryError(
            f"unclassified canonical execution entrypoint: {command!r}"
        )
    return entry


def compatibility_entrypoint_count() -> int:
    return sum(
        entry.classification is DispatchClass.COMPAT_MIGRATION_ONLY
        for entry in INVENTORY
    )


def to_dict() -> dict[str, object]:
    """Return a deterministic machine-readable snapshot for tests/tooling."""

    return {
        "schema": SCHEMA,
        "native_ir_migration_target": NATIVE_IR_MIGRATION_TARGET,
        "compatibility_entrypoint_count": compatibility_entrypoint_count(),
        "entrypoints": [
            {
                "command": entry.command,
                "implementation_symbol": entry.implementation_symbol,
                "classification": entry.classification.value,
                "pipeline": list(entry.pipeline),
                "legacy_fallback": entry.legacy_fallback,
            }
            for entry in INVENTORY
        ],
    }


def validate_inventory() -> None:
    """Reject duplicate, missing or silently broadened public classifications."""

    by_command = inventory_by_command()
    if len(by_command) != len(INVENTORY):
        raise DispatchInventoryError("duplicate canonical execution entrypoint")
    if frozenset(by_command) != PUBLIC_CANONICAL_EXECUTION_COMMANDS:
        missing = sorted(PUBLIC_CANONICAL_EXECUTION_COMMANDS - frozenset(by_command))
        extra = sorted(frozenset(by_command) - PUBLIC_CANONICAL_EXECUTION_COMMANDS)
        raise DispatchInventoryError(
            f"canonical execution inventory mismatch: missing={missing}, extra={extra}"
        )
    for entry in INVENTORY:
        if not entry.implementation_symbol.startswith("koschei."):
            raise DispatchInventoryError(
                f"non-Koschei implementation symbol for {entry.command!r}"
            )
        if not entry.pipeline:
            raise DispatchInventoryError(
                f"empty authority pipeline for {entry.command!r}"
            )


validate_inventory()
