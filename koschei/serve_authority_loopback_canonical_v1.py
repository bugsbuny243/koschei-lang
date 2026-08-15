"""Canonical loopback identity for Serve Authority v1.

The authority layer must not validate the *name* ``localhost`` and later ask the
host resolver what that name means. This guard converts the bootstrap alias to a
literal loopback address before a ServePolicy is created and before manifest scope
is rendered.
"""

from __future__ import annotations

from . import capabilities as _caps
from . import serve_authority_v1 as _serve
from .ast_nodes import Literal

_INSTALLED = False
_ORIGINAL_PARSE = None
_ORIGINAL_RUNTIME_POLICY = None
_ORIGINAL_MANIFEST_SCOPE = None


def _canonical_bind(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    if text.lower().startswith("localhost:"):
        port_text = text[len("localhost:") :]
        if not port_text.isascii() or not port_text.isdigit():
            return None
        port = int(port_text, 10)
        if not 1 <= port <= 65535:
            return None
        return f"127.0.0.1:{port}"
    parsed = _ORIGINAL_PARSE(text)
    if parsed is None:
        return None
    host, port = parsed
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _parse_loopback_bind(raw: str):
    canonical = _canonical_bind(raw)
    if canonical is None:
        return None
    if canonical.startswith("["):
        closing = canonical.index("]")
        return canonical[1:closing], int(canonical[closing + 2 :], 10)
    host, port_text = canonical.rsplit(":", 1)
    return host, int(port_text, 10)


def _runtime_policy(
    bind,
    max_connections,
    max_request_bytes,
    max_response_bytes,
    deadline_ms,
):
    if not isinstance(bind, str):
        return _ORIGINAL_RUNTIME_POLICY(
            bind,
            max_connections,
            max_request_bytes,
            max_response_bytes,
            deadline_ms,
        )
    canonical = _canonical_bind(bind)
    if canonical is None:
        return _ORIGINAL_RUNTIME_POLICY(
            bind,
            max_connections,
            max_request_bytes,
            max_response_bytes,
            deadline_ms,
        )
    return _ORIGINAL_RUNTIME_POLICY(
        canonical,
        max_connections,
        max_request_bytes,
        max_response_bytes,
        deadline_ms,
    )


def _manifest_scope(arguments) -> str:
    if len(arguments) != 5:
        return _caps.DYNAMIC
    bind_expression = arguments[0]
    if not isinstance(bind_expression, Literal) or not isinstance(bind_expression.value, str):
        return _caps.DYNAMIC
    canonical = _canonical_bind(bind_expression.value)
    if canonical is None:
        return _caps.DYNAMIC
    budgets = [_serve._literal_int(item) for item in arguments[1:]]
    if any(value is None for value in budgets):
        return _caps.DYNAMIC
    connections, request_bytes, response_bytes, deadline_ms = budgets
    return (
        f"{canonical} | connections={connections} | request_bytes={request_bytes} | "
        f"response_bytes={response_bytes} | deadline_ms={deadline_ms}"
    )


def install_serve_authority_loopback_canonical_v1() -> None:
    global _INSTALLED, _ORIGINAL_PARSE, _ORIGINAL_RUNTIME_POLICY, _ORIGINAL_MANIFEST_SCOPE
    if _INSTALLED:
        return

    _ORIGINAL_PARSE = _serve._parse_loopback_bind
    _serve._parse_loopback_bind = _parse_loopback_bind

    _ORIGINAL_RUNTIME_POLICY = _serve._runtime_policy
    _serve._runtime_policy = _runtime_policy

    _ORIGINAL_MANIFEST_SCOPE = _serve._serve_manifest_scope
    _serve._serve_manifest_scope = _manifest_scope

    _INSTALLED = True
