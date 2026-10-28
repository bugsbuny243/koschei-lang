"""Truthful stdlib catalog overlay for experimental loopback ingress.

The catalog's `supported` state means executed interpreter/native-Go parity, not
merely that two backend implementations exist in source. Exchange v1 now has an
interpreter implementation plus a Linux native-Go implementation and parity tests,
but hosted CI has not executed those gates because runner allocation is blocked.
It therefore remains `reserved`.
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
                    "Interpreter and Linux native-Go implementations plus parity tests "
                    "exist, including exact backlog, byte and I/O-deadline contracts. "
                    "The operation remains reserved until real CI executes those gates."
                ),
            ),
            *(
                _catalog.Operation(
                    name=name,
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
                        "Multi-request loopback server (serve_knowhere_v1): every budget is "
                        "enforced under ks run and in native binaries through the capability "
                        "broker, tested with real clients; reply_as names the response "
                        "content type and reply_with adds checked headers. The operation stays reserved like the rest of the "
                        "family."
                    ),
                )
                for name in ("accept", "reply", "reply_as", "reply_with")
            ),
        ),
    )

    _catalog.CATALOG = tuple(
        replacement if family.name == "serve" else family
        for family in _catalog.CATALOG
    )
    _catalog.validate_catalog(_catalog.CATALOG)
    _INSTALLED = True
