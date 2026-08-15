"""Truthful stdlib catalog overlay for experimental loopback ingress.

The catalog's `supported` state means interpreter/native-Go parity. Exchange v1 is
intentionally interpreter-only while the native listener ABI remains fail-closed,
so it is recorded as `reserved`, never `supported`.
"""

from __future__ import annotations

from . import stdlib_catalog as _catalog

_INSTALLED = False


def install_serve_loopback_exchange_catalog_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    replacement = _catalog.Family(
        name="serve",
        status="partial",
        target="v1",
        purpose=(
            "Capability-bound loopback HTTP ingress with explicit connection, byte "
            "and I/O-deadline budgets."
        ),
        operations=(
            _catalog.Operation(
                name="exchange",
                status="reserved",
                interpreter=False,
                native_go=False,
                capability="ServeCaps",
                required_budgets=(
                    "connections",
                    "request_bytes",
                    "response_bytes",
                    "deadline",
                ),
                enforced_budgets=(),
                security_sensitive=True,
                note=(
                    "Experimental interpreter path enforces the authority budgets for "
                    "a one-shot loopback exchange, but the stdlib catalog does not "
                    "claim backend support until native-Go parity exists."
                ),
            ),
            _catalog.Operation(
                name="listen",
                status="planned",
                capability="ServeCaps",
                required_budgets=(
                    "connections",
                    "request_bytes",
                    "response_bytes",
                    "deadline",
                ),
                security_sensitive=True,
                note=(
                    "Long-running handler/listener API remains planned; callback lifetime "
                    "and structured cancellation are not implied by exchange v1."
                ),
            ),
        ),
    )

    _catalog.CATALOG = tuple(
        replacement if family.name == "serve" else family
        for family in _catalog.CATALOG
    )
    _catalog.validate_catalog(_catalog.CATALOG)
    _INSTALLED = True
