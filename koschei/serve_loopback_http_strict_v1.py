"""Strict HTTP/1.x preflight for one-shot loopback exchange v1.

This layer intentionally accepts a smaller grammar than general-purpose HTTP
servers. Reducing parser ambiguity is preferable to accepting unusual syntax in a
security bootstrap primitive.
"""

from __future__ import annotations

from . import interpreter as _runtime
from . import serve_loopback_exchange_v1 as _exchange

_TOKEN = frozenset(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)
_INSTALLED = False
_ORIGINAL_PARSE_REQUEST_HEAD = None


def _valid_token(value: str) -> bool:
    return bool(value) and all(character in _TOKEN for character in value)


def _valid_header_value(value: str) -> bool:
    return all(
        (character == "\t") or (0x20 <= ord(character) <= 0x7E) or (0x80 <= ord(character) <= 0xFF)
        for character in value
    )


def _parse_request_head(raw: bytes):
    marker = raw.find(b"\r\n\r\n")
    if marker < 0:
        return _ORIGINAL_PARSE_REQUEST_HEAD(raw)
    if marker + 4 > _exchange._MAX_HEADER_BYTES:
        return _exchange._protocol_error("HTTP headers exceed the hard header limit")

    head = raw[:marker]
    try:
        text = head.decode("iso-8859-1")
    except UnicodeDecodeError:
        return _exchange._protocol_error("HTTP headers are not decodable")

    lines = text.split("\r\n")
    if not lines or not lines[0]:
        return _exchange._protocol_error("HTTP request line is missing")

    request_parts = lines[0].split(" ")
    if len(request_parts) != 3:
        return _exchange._protocol_error(
            "HTTP request line must contain method, target and version"
        )
    method, target, version = request_parts
    if not method.isascii() or not method.isalpha() or not method.isupper():
        return _exchange._protocol_error(
            "exchange v1 accepts uppercase alphabetic HTTP methods only"
        )
    if (
        not target
        or not target.isascii()
        or not target.startswith("/")
        or "#" in target
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in target)
    ):
        return _exchange._protocol_error(
            "exchange v1 requires a printable ASCII origin-form request target"
        )
    if version not in {"HTTP/1.0", "HTTP/1.1"}:
        return _exchange._protocol_error(
            "only HTTP/1.0 and HTTP/1.1 are accepted"
        )

    hosts = 0
    content_lengths = 0
    for line in lines[1:]:
        if not line or ":" not in line:
            return _exchange._protocol_error("malformed HTTP header line")
        raw_name, raw_value = line.split(":", 1)
        if raw_name != raw_name.strip() or not _valid_token(raw_name):
            return _exchange._protocol_error("malformed HTTP header name")
        value = raw_value.strip(" \t")
        if not _valid_header_value(value):
            return _exchange._protocol_error("HTTP header value contains a control byte")

        name = raw_name.lower()
        if name == "host":
            hosts += 1
        elif name == "content-length":
            content_lengths += 1
        elif name == "transfer-encoding":
            # Keep the rejection here as well as in the base parser so future
            # refactors cannot accidentally weaken the no-TE rule.
            return _exchange._protocol_error(
                "Transfer-Encoding is not supported by exchange v1"
            )

    if version == "HTTP/1.1" and hosts != 1:
        return _exchange._protocol_error(
            "HTTP/1.1 exchange v1 requires exactly one Host header"
        )
    if hosts > 1:
        return _exchange._protocol_error("duplicate Host headers are rejected")
    if content_lengths > 1:
        return _exchange._protocol_error(
            "duplicate Content-Length headers are rejected"
        )

    return _ORIGINAL_PARSE_REQUEST_HEAD(raw)


def install_serve_loopback_http_strict_v1() -> None:
    global _INSTALLED, _ORIGINAL_PARSE_REQUEST_HEAD
    if _INSTALLED:
        return
    _ORIGINAL_PARSE_REQUEST_HEAD = _exchange._parse_request_head
    _exchange._parse_request_head = _parse_request_head
    _INSTALLED = True
