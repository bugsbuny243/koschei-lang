"""Public Serve binds: `0.0.0.0:PORT` and `[::]:PORT`.

Serve Authority v1 accepted loopback binds only. A web application has to
listen where its users can reach it, so a server may also bind every
interface, spelled exactly `0.0.0.0:PORT` (IPv4) or `[::]:PORT` (IPv6, which
on Linux also takes IPv4 connections). The bind is still a compile-time literal
(`KS2410`), so `ks caps` names it before the program runs and
`ks caps --deny serve` refuses it. Any other non-loopback address stays
`KS2411`: a program binds one machine-local interface or all of them, never an
address whose meaning depends on the host's network setup.

Every budget, the strict HTTP/1.x grammar and the one-request-per-connection
rule are unchanged. The native broker ports the same rule
(`native_serve_v1._ksParseLoopbackBind`).
"""

from __future__ import annotations

import re
from typing import Any, Callable

_PUBLIC = re.compile(r"(0\.0\.0\.0|\[::\]):([0-9]{1,5})")
_INSTALLED = False


def parse_public_bind(raw: Any) -> tuple[str, int] | None:
    """("0.0.0.0" or "::", port) for an exact public bind, else None."""

    if not isinstance(raw, str):
        return None
    match = _PUBLIC.fullmatch(raw.strip())
    if match is None:
        return None
    port = int(match.group(2), 10)
    if not 1 <= port <= 65535:
        return None
    host = "0.0.0.0" if match.group(1) == "0.0.0.0" else "::"
    return host, port


def is_public_bind(raw: Any) -> bool:
    return parse_public_bind(raw) is not None


def _public_aware(original: Callable[[str], Any]) -> Callable[[str], Any]:
    if getattr(original, "_koschei_public_bind", False):
        return original

    def parse(raw: str):
        public = parse_public_bind(raw)
        if public is not None:
            return public
        return original(raw)

    parse._koschei_public_bind = True  # type: ignore[attr-defined]
    return parse


def install_serve_public_bind_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import serve_authority_loopback_canonical_v1 as _canonical
    from . import serve_authority_v1 as _authority
    from . import serve_knowhere_v1 as _knowhere
    from . import serve_loopback_exchange_v1 as _exchange

    # The canonical layer renders manifest scopes and runtime policies from the
    # parser it wrapped; the other modules hold the parser by name.
    _canonical._ORIGINAL_PARSE = _public_aware(_canonical._ORIGINAL_PARSE)
    for module in (_authority, _knowhere, _exchange):
        module._parse_loopback_bind = _public_aware(module._parse_loopback_bind)
    _INSTALLED = True
