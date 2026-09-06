"""Fail-closed boot gate for Koschei runtime execution.

The runtime implementation provides value/capability primitives; canonical
contracts own language authority and boundary policy. Every public runtime
entrypoint that executes checked MIR must pass through this gate before any user
program receives a SystemCaps value.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from .runtime_bridge_seal_v1 import (
    RuntimeBridgeSealError,
    require_runtime_bridge_sealed,
)
from .runtime_capability_registry_v1 import (
    RuntimeCapabilityRegistry,
    validate_runtime_module,
)
from .runtime_interpreter_bridge_v1 import (
    RuntimeAuthorityError,
    install_canonical_authority_bridge,
)
from .runtime_network_policy_bridge_v1 import (
    RuntimeNetworkPolicyError,
    bind_canonical_network_policy,
    require_canonical_network_policy,
)


class RuntimeBootError(RuntimeError):
    """Raised when runtime implementation and canonical contracts diverge."""


def require_runtime_ready(runtime: ModuleType) -> RuntimeCapabilityRegistry:
    """Validate, bind and seal canonical runtime contracts before execution."""

    try:
        registry = validate_runtime_module(runtime)
        install_canonical_authority_bridge(runtime)
        require_runtime_bridge_sealed(runtime)
        bind_canonical_network_policy(runtime)
        require_canonical_network_policy(runtime)
    except (
        RuntimeError,
        RuntimeAuthorityError,
        RuntimeBridgeSealError,
        RuntimeNetworkPolicyError,
    ) as error:
        raise RuntimeBootError(f"KOSCHEI RUNTIME BOOT DENIED: {error}") from error
    return registry


def run_checked_mir(mir_graph: Any, argv: list[str] | None = None) -> int:
    """Execute sealed MIR after runtime validation and canonical binding.

    The boot gate still validates the runtime capability implementation, but user
    code is executed by the sealed MIR v4 executor. There is no AST execution
    fallback from this public checked-MIR path.
    """

    from . import interpreter
    from .mir_executor_v1 import execute_mir_v1

    require_runtime_ready(interpreter)
    result = execute_mir_v1(mir_graph, list(argv or []))
    if isinstance(result, interpreter.KsError):
        import sys

        print(f"KOSCHEI RUNTIME ERROR: {result.message}", file=sys.stderr)
        return 1
    return 0
