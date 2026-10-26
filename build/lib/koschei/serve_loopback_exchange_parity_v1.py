"""Interpreter/native parity guard for one-shot Serve exchange v1.

Two details are security-visible and therefore cannot drift by backend:

- HTTP/1.1 Host must be present exactly once *and non-empty*.
- max_connections is the exact listener backlog budget, not merely an upper bound
  that one backend silently clamps to a smaller implementation default.
"""

from __future__ import annotations

import socket
import time
from typing import Any

from . import interpreter as _runtime
from . import serve_loopback_exchange_v1 as _exchange
from .serve_authority_v1 import ServeCaps

_INSTALLED = False
_ORIGINAL_PARSE = None


def _parse_request_head(raw: bytes):
    result = _ORIGINAL_PARSE(raw)
    if isinstance(result, _runtime.KsError):
        return result

    marker = raw.find(b"\r\n\r\n")
    if marker < 0:
        return result
    try:
        lines = raw[:marker].decode("iso-8859-1").split("\r\n")
    except UnicodeDecodeError:
        return _exchange._protocol_error("HTTP headers are not decodable")

    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        if name.lower() == "host" and value.strip(" \t") == "":
            return _exchange._protocol_error("Host header may not be empty")
    return result


def _exchange_exact_backlog(
    self: ServeCaps,
    response_body: Any,
) -> str | _runtime.KsError:
    if not isinstance(response_body, str):
        return _exchange._protocol_error("ServeCaps.exchange() response must be String")

    wire = _exchange._response_wire(response_body, self.policy)
    if isinstance(wire, _runtime.KsError):
        return wire

    parsed = _exchange._parse_loopback_bind(self.policy.bind)
    if parsed is None:
        return _exchange._protocol_error("sealed ServeCaps bind is invalid")
    host, port = parsed
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    deadline = time.monotonic() + (self.policy.deadline_ms / 1000.0)

    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            _exchange._apply_deadline(listener, deadline)
            listener.bind((host, port))
            listener.listen(self.policy.max_connections)
            _exchange._apply_deadline(listener, deadline)
            try:
                connection, _peer = listener.accept()
            except socket.timeout:
                return _exchange._io_error("accept exceeded the I/O deadline")

            with connection:
                request_body = _exchange._read_one_request(
                    connection,
                    self.policy,
                    deadline,
                )
                if isinstance(request_body, _runtime.KsError):
                    return request_body
                _exchange._apply_deadline(connection, deadline)
                try:
                    connection.sendall(wire)
                except socket.timeout:
                    return _exchange._io_error(
                        "response write exceeded the I/O deadline"
                    )
                except OSError as error:
                    return _exchange._io_error(f"response write failed: {error}")
                return request_body
    except TimeoutError:
        return _exchange._io_error("I/O deadline expired")
    except OSError as error:
        return _exchange._io_error(f"listener failed: {error}")


def install_serve_loopback_exchange_parity_v1() -> None:
    global _INSTALLED, _ORIGINAL_PARSE
    if _INSTALLED:
        return

    _ORIGINAL_PARSE = _exchange._parse_request_head
    _exchange._parse_request_head = _parse_request_head

    _exchange._exchange = _exchange_exact_backlog
    ServeCaps.exchange = _exchange_exact_backlog

    _INSTALLED = True
