"""One-shot bounded loopback HTTP ingress for the provisional Serve authority.

`ServeCaps.exchange(response)` is intentionally smaller than a server framework:
it accepts exactly one connection, reads exactly one HTTP/1.x request under the
sealed byte/I/O budgets, writes one fixed text response, closes the connection and
returns the UTF-8 request body.

There is no user callback in this slice, so the I/O deadline is not misrepresented
as a handler CPU deadline. Public binds remain impossible because ServeCaps can
only be created by Serve Authority v1's loopback policy.
"""

from __future__ import annotations

import socket
import time
from typing import Any

from . import semantic as _semantic
from . import interpreter as _runtime
from .serve_authority_v1 import ServeCaps, ServePolicy, _parse_loopback_bind

_MAX_HEADER_BYTES = 64 * 1024
_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Serve I/O deadline expired")
    return remaining


def _apply_deadline(sock: socket.socket, deadline: float) -> None:
    sock.settimeout(_remaining_seconds(deadline))


def _protocol_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3410: {message}")


def _io_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3411: {message}")


def _parse_request_head(raw: bytes) -> tuple[int, int] | _runtime.KsError:
    """Return (header_end_index, content_length) for one strict HTTP request."""

    marker = raw.find(b"\r\n\r\n")
    if marker < 0:
        return _protocol_error("HTTP header terminator was not found")

    head = raw[:marker]
    try:
        text = head.decode("iso-8859-1")
    except UnicodeDecodeError:
        return _protocol_error("HTTP headers are not decodable")

    lines = text.split("\r\n")
    if not lines or not lines[0]:
        return _protocol_error("HTTP request line is missing")
    request_parts = lines[0].split(" ")
    if len(request_parts) != 3:
        return _protocol_error("HTTP request line must contain method, target and version")
    method, target, version = request_parts
    if not method or not method.isascii() or not method.isupper():
        return _protocol_error("HTTP method must be an uppercase ASCII token")
    if not target.startswith("/") or " " in target:
        return _protocol_error("only origin-form HTTP request targets are accepted")
    if version not in {"HTTP/1.0", "HTTP/1.1"}:
        return _protocol_error("only HTTP/1.0 and HTTP/1.1 are accepted")

    content_lengths: list[str] = []
    transfer_encoding = False
    for line in lines[1:]:
        if not line or ":" not in line:
            return _protocol_error("malformed HTTP header line")
        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()
        if not name or any(char.isspace() for char in name):
            return _protocol_error("malformed HTTP header name")
        if name == "transfer-encoding":
            transfer_encoding = True
        elif name == "content-length":
            content_lengths.append(value)

    if transfer_encoding:
        return _protocol_error("Transfer-Encoding is not supported by exchange v1")

    content_length = 0
    if content_lengths:
        if len(set(content_lengths)) != 1:
            return _protocol_error("conflicting Content-Length headers are rejected")
        raw_length = content_lengths[0]
        if not raw_length.isascii() or not raw_length.isdigit():
            return _protocol_error("Content-Length must be a non-negative decimal integer")
        try:
            content_length = int(raw_length, 10)
        except ValueError:
            return _protocol_error("Content-Length is invalid")

    return marker + 4, content_length


def _read_one_request(
    connection: socket.socket,
    policy: ServePolicy,
    deadline: float,
) -> str | _runtime.KsError:
    buffer = bytearray()
    header_limit = min(policy.max_request_bytes, _MAX_HEADER_BYTES)
    body_start: int | None = None
    content_length: int | None = None

    while body_start is None:
        if len(buffer) >= header_limit:
            return _protocol_error("HTTP headers exceed the configured request budget")
        _apply_deadline(connection, deadline)
        try:
            chunk = connection.recv(min(4096, header_limit - len(buffer) + 1))
        except socket.timeout:
            return _io_error("request header read exceeded the I/O deadline")
        except OSError as error:
            return _io_error(f"request header read failed: {error}")
        if not chunk:
            return _protocol_error("connection closed before HTTP headers completed")
        buffer.extend(chunk)
        if len(buffer) > policy.max_request_bytes:
            return _protocol_error("request exceeds max_request_bytes")
        marker = buffer.find(b"\r\n\r\n")
        if marker >= 0:
            parsed = _parse_request_head(bytes(buffer))
            if isinstance(parsed, _runtime.KsError):
                return parsed
            body_start, content_length = parsed

    assert content_length is not None
    expected_total = body_start + content_length
    if expected_total > policy.max_request_bytes:
        return _protocol_error("request body exceeds max_request_bytes")
    if len(buffer) > expected_total:
        return _protocol_error("HTTP pipelining or bytes beyond Content-Length are rejected")

    while len(buffer) < expected_total:
        _apply_deadline(connection, deadline)
        remaining = expected_total - len(buffer)
        try:
            chunk = connection.recv(min(4096, remaining + 1))
        except socket.timeout:
            return _io_error("request body read exceeded the I/O deadline")
        except OSError as error:
            return _io_error(f"request body read failed: {error}")
        if not chunk:
            return _protocol_error("connection closed before request body completed")
        buffer.extend(chunk)
        if len(buffer) > expected_total:
            return _protocol_error("bytes beyond declared Content-Length are rejected")

    body = bytes(buffer[body_start:expected_total])
    try:
        return body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _protocol_error("exchange v1 request body must be valid UTF-8")


def _response_wire(response_body: str, policy: ServePolicy) -> bytes | _runtime.KsError:
    payload = response_body.encode("utf-8")
    head = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    wire = head + payload
    if len(wire) > policy.max_response_bytes:
        return _protocol_error("response exceeds max_response_bytes")
    return wire


def _exchange(self: ServeCaps, response_body: Any) -> str | _runtime.KsError:
    if not isinstance(response_body, str):
        return _protocol_error("ServeCaps.exchange() response must be String")

    wire = _response_wire(response_body, self.policy)
    if isinstance(wire, _runtime.KsError):
        return wire

    parsed = _parse_loopback_bind(self.policy.bind)
    if parsed is None:
        return _protocol_error("sealed ServeCaps bind is invalid")
    host, port = parsed
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    deadline = time.monotonic() + (self.policy.deadline_ms / 1000.0)

    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _apply_deadline(listener, deadline)
            listener.bind((host, port))
            listener.listen(min(self.policy.max_connections, 128))
            _apply_deadline(listener, deadline)
            try:
                connection, _peer = listener.accept()
            except socket.timeout:
                return _io_error("accept exceeded the I/O deadline")

            with connection:
                request_body = _read_one_request(connection, self.policy, deadline)
                if isinstance(request_body, _runtime.KsError):
                    return request_body
                _apply_deadline(connection, deadline)
                try:
                    connection.sendall(wire)
                except socket.timeout:
                    return _io_error("response write exceeded the I/O deadline")
                except OSError as error:
                    return _io_error(f"response write failed: {error}")
                return request_body
    except TimeoutError:
        return _io_error("I/O deadline expired")
    except OSError as error:
        return _io_error(f"listener failed: {error}")


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "ServeCaps" and method_name == "exchange":
        values = argument_types or []
        if len(values) != 1:
            raise _semantic.SemanticError(
                "KS1301",
                f"ServeCaps.exchange() 1 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(
            ("String",),
            values[0],
            "ServeCaps.exchange() yanıtı",
            location,
        )
        return "String or Error"
    return _ORIGINAL_CHECK_METHOD_CALL(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def install_serve_loopback_exchange_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_METHOD_CALL
    if _INSTALLED:
        return

    _semantic.NARROWED_METHODS["ServeCaps"].add("exchange")
    _semantic.GUARDED_METHODS.add("exchange")
    ServeCaps.exchange = _exchange

    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call

    _INSTALLED = True
