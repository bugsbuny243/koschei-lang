"""Fail-closed boot gate for Koschei runtime execution.

The interpreter provides implementations; the canonical capability contract owns
language authority. Every public runtime entrypoint that executes checked MIR
must pass through this gate before any user program receives a SystemCaps value.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from .capability_effect_contract_v1 import NET_ORIGIN_SCHEMES
from .runtime_capability_registry_v1 import (
    RuntimeCapabilityRegistry,
    validate_runtime_module,
)
from .runtime_interpreter_bridge_v1 import (
    RuntimeAuthorityError,
    install_canonical_authority_bridge,
)


class RuntimeBootError(RuntimeError):
    """Raised when runtime implementation and canonical authority contract diverge."""


def require_runtime_ready(runtime: ModuleType) -> RuntimeCapabilityRegistry:
    """Validate and bind canonical authority before execution.

    This intentionally re-validates at each execution boundary. A long-lived
    process may have imported or monkey-patched modules after startup; successful
    validation once is not a permanent trust grant.
    """

    try:
        registry = validate_runtime_module(runtime)
        install_canonical_authority_bridge(runtime)
    except (RuntimeError, RuntimeAuthorityError) as error:
        raise RuntimeBootError(f"KOSCHEI RUNTIME BOOT DENIED: {error}") from error

    runtime_schemes = getattr(runtime, "ALLOWED_NET_SCHEMES", None)
    if runtime_schemes is None:
        raise RuntimeBootError(
            "KOSCHEI RUNTIME BOOT DENIED: runtime network authority policy missing"
        )
    if frozenset(runtime_schemes) != NET_ORIGIN_SCHEMES:
        raise RuntimeBootError(
            "KOSCHEI RUNTIME BOOT DENIED: runtime network authority policy drift"
        )
    return registry


def run_checked_mir(mir_graph: Any, argv: list[str] | None = None) -> int:
    """Execute sealed MIR only after runtime validation and authority binding."""

    # Local import avoids interpreter <-> boot-gate import cycles.
    from . import interpreter

    require_runtime_ready(interpreter)
    return interpreter.run_mir(mir_graph, list(argv or []))
