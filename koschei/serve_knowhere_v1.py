"""Multi-request loopback server v1: the Knowhere and Sakaar laws (gate G4).

The program stays in control; there is no callback::

    fn main(caps: SystemCaps) {
        let server = caps.serve.allow("127.0.0.1:8080", 100, 65536, 65536, 5000)
        let mut served = 0
        while served < 100 {
            let request = server.accept() or return
            let answer = "{request.method()} {request.path()}"
            server.reply(200, answer) or return
            served = served + 1
        }
    }

``accept()`` opens the sealed loopback listener on first use and keeps it,
accepts one connection, reads one strict HTTP/1.x request and returns it as an
``HttpRequest`` value. ``reply(status, body)`` answers that request and closes
its connection.

**Knowhere: nothing survives from one request to the next.** Each connection
carries exactly one request. A request is answered once; ``accept()`` while
one is still unanswered closes it with ``500`` and returns ``KS3470``, so an
unanswered client is never left waiting and never answered later by mistake.
A request that breaks the protocol or its budget is answered ``400``/``413``
and ``accept()`` returns the Error value; the server keeps listening.

**Sakaar: no implicit input processing.** The program sees the method, the
raw path (query string included, nothing decoded), header values by exact
name and the body; there is no routing, cookie, form or JSON parsing.

Budgets from ``caps.serve.allow(bind, max_connections, max_request_bytes,
max_response_bytes, deadline_ms)``: ``max_connections`` requests in total
(then ``KS3471``), request and response bytes per request, and
``deadline_ms`` per request, applied to waiting in ``accept()`` and to the
whole read of one request.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import time
from typing import Any

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import semantic as _semantic
from . import serve_loopback_exchange_v1 as _exchange
from . import type_contracts as _contracts
from . import _typed_expr
from . import _typed_ops
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .serve_authority_v1 import ServeCaps, _parse_loopback_bind
from .type_system import ERROR, STRING, NamedType, VOID, union_type

HTTP_REQUEST = NamedType("HttpRequest")
REQUEST_METHODS = {"method": 0, "path": 0, "body": 0, "body_bytes": 0, "header": 1}

PENDING_MESSAGE = "KS3470: Önceki istek yanıtlanmadan yeni istek kabul edilemez; önceki istek 500 ile kapatıldı."
NO_PENDING_MESSAGE = "KS3470: Yanıtlanacak bekleyen bir istek yok."
BUDGET_MESSAGE = "KS3471: Sunucunun istek bütçesi tükendi: en fazla {count} istek kabul edilebilir."
STATUS_MESSAGE = "KS3472: Desteklenmeyen HTTP durum kodu: {status}."
EMPTY_BODY_MESSAGE = "KS3472: 204 yanıtı gövde taşıyamaz."
HEADER_MESSAGE = "KS3473: İstekte '{name}' başlığı yok."
BODY_TEXT_MESSAGE = "KS3430: İstek gövdesi geçerli UTF-8 metin değil."

REASONS = {
    200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 409: "Conflict", 413: "Content Too Large",
    422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error",
    503: "Service Unavailable",
}

_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """One received request: data only, no connection and no authority."""

    method_name: str
    raw_path: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def __str__(self) -> str:
        return f"HttpRequest({self.method_name} {self.raw_path})"

    __repr__ = __str__


class _Server:
    __slots__ = ("listener", "pending", "accepted")

    def __init__(self, listener: socket.socket) -> None:
        self.listener = listener
        self.pending: socket.socket | None = None
        self.accepted = 0


def _wire(status: int, body: bytes) -> bytes:
    head = (
        f"HTTP/1.1 {status} {REASONS[status]}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    return head + body


def _close(connection: socket.socket, status: int | None = None, deadline: float | None = None) -> None:
    try:
        if status is not None:
            connection.settimeout(1.0 if deadline is None else max(deadline - time.monotonic(), 0.01))
            connection.sendall(_wire(status, REASONS[status].encode("ascii")))
    except OSError:
        pass
    finally:
        try:
            connection.close()
        except OSError:
            pass


def _open(caps: ServeCaps) -> _Server | _runtime.KsError:
    parsed = _parse_loopback_bind(caps.policy.bind)
    if parsed is None:
        return _exchange._protocol_error("sealed ServeCaps bind is invalid")
    host, port = parsed
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(min(caps.policy.max_connections, 128))
    except OSError as error:
        listener.close()
        return _exchange._io_error(f"listener failed: {error}")
    return _Server(listener)


def _parse_headers(raw_head: bytes) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    lines = raw_head.decode("iso-8859-1").split("\r\n")
    method, target, _version = lines[0].split(" ")
    headers = []
    for line in lines[1:]:
        name, value = line.split(":", 1)
        headers.append((name.lower(), value.strip(" \t")))
    return method, target, tuple(headers)


def _read_request(connection: socket.socket, caps: ServeCaps, deadline: float):
    """(HttpRequest, None) or (None, (status, KsError))."""

    policy = caps.policy
    buffer = bytearray()
    header_limit = min(policy.max_request_bytes, _exchange._MAX_HEADER_BYTES)
    try:
        while True:
            marker = buffer.find(b"\r\n\r\n")
            if marker >= 0:
                break
            if len(buffer) >= header_limit:
                return None, (413, _exchange._protocol_error("HTTP headers exceed the configured request budget"))
            _exchange._apply_deadline(connection, deadline)
            chunk = connection.recv(min(4096, header_limit - len(buffer) + 1))
            if not chunk:
                return None, (400, _exchange._protocol_error("connection closed before HTTP headers completed"))
            buffer.extend(chunk)
        parsed = _exchange._parse_request_head(bytes(buffer))
        if isinstance(parsed, _runtime.KsError):
            return None, (400, parsed)
        body_start, content_length = parsed
        expected = body_start + content_length
        if expected > policy.max_request_bytes:
            return None, (413, _exchange._protocol_error("request body exceeds max_request_bytes"))
        if len(buffer) > expected:
            return None, (400, _exchange._protocol_error("HTTP pipelining or bytes beyond Content-Length are rejected"))
        while len(buffer) < expected:
            _exchange._apply_deadline(connection, deadline)
            chunk = connection.recv(min(4096, expected - len(buffer) + 1))
            if not chunk:
                return None, (400, _exchange._protocol_error("connection closed before request body completed"))
            buffer.extend(chunk)
            if len(buffer) > expected:
                return None, (400, _exchange._protocol_error("bytes beyond declared Content-Length are rejected"))
    except (socket.timeout, TimeoutError):
        return None, (400, _exchange._io_error("request read exceeded the I/O deadline"))
    except OSError as error:
        return None, (400, _exchange._io_error(f"request read failed: {error}"))
    method, target, headers = _parse_headers(bytes(buffer[: body_start - 4]))
    return HttpRequest(method, target, headers, bytes(buffer[body_start:expected])), None


def _accept(self: ServeCaps):
    server = self._server
    if server is None:
        opened = _open(self)
        if isinstance(opened, _runtime.KsError):
            return opened
        self._server = server = opened
    if server.pending is not None:
        _close(server.pending, 500)
        server.pending = None
        return _runtime.KsError(PENDING_MESSAGE)
    if server.accepted >= self.policy.max_connections:
        return _runtime.KsError(BUDGET_MESSAGE.format(count=self.policy.max_connections))
    deadline = time.monotonic() + self.policy.deadline_ms / 1000.0
    try:
        _exchange._apply_deadline(server.listener, deadline)
        connection, _peer = server.listener.accept()
    except (socket.timeout, TimeoutError):
        return _exchange._io_error("accept exceeded the I/O deadline")
    except OSError as error:
        return _exchange._io_error(f"accept failed: {error}")
    server.accepted += 1
    request, failure = _read_request(connection, self, deadline)
    if failure is not None:
        status, error = failure
        _close(connection, status, deadline)
        return error
    server.pending = connection
    return request


def _reply(self: ServeCaps, status: Any, body: Any):
    server = self._server
    if server is None or server.pending is None:
        return _runtime.KsError(NO_PENDING_MESSAGE)
    connection = server.pending
    server.pending = None
    if type(status) is not int or status not in REASONS:
        _close(connection, 500)
        return _runtime.KsError(STATUS_MESSAGE.format(status=status))
    if not isinstance(body, (str, bytes)):
        _close(connection, 500)
        return _exchange._protocol_error("ServeCaps.reply() body must be String or Bytes")
    payload = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    if status == 204 and payload:
        _close(connection, 500)
        return _runtime.KsError(EMPTY_BODY_MESSAGE)
    wire = _wire(status, payload)
    if len(wire) > self.policy.max_response_bytes:
        _close(connection, 500)
        return _exchange._protocol_error("response exceeds max_response_bytes")
    try:
        connection.settimeout(self.policy.deadline_ms / 1000.0)
        connection.sendall(wire)
    except (socket.timeout, TimeoutError):
        return _exchange._io_error("response write exceeded the I/O deadline")
    except OSError as error:
        return _exchange._io_error(f"response write failed: {error}")
    finally:
        _close(connection)
    return _runtime.KsUnit


def request_method(request: HttpRequest, name: str, arguments: list[Any]) -> Any:
    if name == "method":
        return request.method_name
    if name == "path":
        return request.raw_path
    if name == "body":
        try:
            return request.body.decode("utf-8")
        except UnicodeDecodeError:
            return _runtime.KsError(BODY_TEXT_MESSAGE)
    if name == "body_bytes":
        return _runtime.Bytes(request.body)
    if name == "header":
        (wanted,) = arguments
        if not isinstance(wanted, str):
            return _runtime.KsError(HEADER_MESSAGE.format(name=wanted))
        for header, value in request.headers:
            if header == wanted.lower():
                return value
        return _runtime.KsError(HEADER_MESSAGE.format(name=wanted))
    raise AssertionError(name)


# ---- checking ---------------------------------------------------------------


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    values = argument_types or []
    if receiver_type == "ServeCaps" and method_name in {"accept", "reply"}:
        expected = 0 if method_name == "accept" else 2
        if len(values) != expected:
            raise _semantic.SemanticError(
                "KS1301", f"ServeCaps.{method_name}() {expected} argüman bekler, {len(values)} verildi.", location
            )
        if method_name == "reply":
            self._require_assignable(("Int",), values[0], "ServeCaps.reply() durum kodu", location)
            self._require_assignable(("String", "Bytes"), values[1], "ServeCaps.reply() gövdesi", location)
            return "Void or Error"
        return "HttpRequest or Error"
    if receiver_type == "HttpRequest":
        expected = REQUEST_METHODS.get(method_name)
        if expected is None:
            raise _semantic.SemanticError(
                "KS1502",
                f"HttpRequest üzerinde '{method_name}' metodu yok. "
                f"Kullanılabilir: {', '.join(sorted(REQUEST_METHODS))}.",
                location,
            )
        if len(values) != expected:
            raise _semantic.SemanticError(
                "KS1301", f"HttpRequest.{method_name}() {expected} argüman bekler, {len(values)} verildi.", location
            )
        if method_name == "header":
            self._require_assignable(("String",), values[0], "HttpRequest.header() adı", location)
        return {
            "method": "String",
            "path": "String",
            "body": "String or Error",
            "body_bytes": "Bytes",
            "header": "String or Error",
        }[method_name]
    return _ORIGINALS["check_method_call"](self, receiver_type, method_name, location, argument_types, arguments)


def _semantic_fallible(self, expression):
    callee = getattr(expression, "callee", None)
    if hasattr(callee, "member") and callee.member in {"body", "header"}:
        if self._receiver_type(callee.object) == "HttpRequest":
            return True
    return _ORIGINALS["semantic_fallible"](self, expression)


_TYPED = {
    ("ServeCaps", "accept"): (0, union_type(HTTP_REQUEST, ERROR)),
    ("ServeCaps", "reply"): (2, union_type(VOID, ERROR)),
    ("HttpRequest", "method"): (0, STRING),
    ("HttpRequest", "path"): (0, STRING),
    ("HttpRequest", "body"): (0, union_type(STRING, ERROR)),
    ("HttpRequest", "body_bytes"): (0, NamedType("Bytes")),
    ("HttpRequest", "header"): (1, union_type(STRING, ERROR)),
}


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType):
        typed = _TYPED.get((receiver.name, method))
        if typed is not None:
            expected, result = typed
            if len(arguments) != expected:
                raise _semantic.SemanticError(
                    "KS1301", f"{receiver.name}.{method}() {expected} argüman bekler, {len(arguments)} verildi.", location
                )
            return result
        if receiver.name == "HttpRequest":
            raise _semantic.SemanticError(
                "KS1306", f"'{method}' işlemi HttpRequest tipi için güvenli değildir.", location
            )
    return _ORIGINALS["method_type"](receiver, method, arguments, location)


# ---- runtimes ---------------------------------------------------------------


def _member(self, receiver, name, location):
    if isinstance(receiver, ServeCaps) and name in {"accept", "reply"}:
        return _runtime._BoundMember(receiver, name, location)
    if isinstance(receiver, HttpRequest) and name in REQUEST_METHODS:
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINALS["member"](self, receiver, name, location)


def _invoke_member(self, member, arguments):
    if isinstance(member.receiver, HttpRequest) and member.name in REQUEST_METHODS:
        self._require_arity(member.name, arguments, REQUEST_METHODS[member.name], member.location)
        return request_method(member.receiver, member.name, arguments)
    return _ORIGINALS["invoke_member"](self, member, arguments)


def _facade_member_allowed(cls, member):
    if isinstance(member.receiver, HttpRequest):
        return member.name in REQUEST_METHODS
    return _ORIGINALS["facade_member_allowed"].__func__(cls, member)


def _runtime_matches(self, value, expected_names, *, type_parameters=frozenset(), type_bindings=None):
    if isinstance(value, HttpRequest) and "HttpRequest" in tuple(expected_names):
        return True
    return _ORIGINALS["runtime_matches"](
        self, value, expected_names, type_parameters=type_parameters, type_bindings=type_bindings
    )


def install_serve_knowhere_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ServeCaps.accept = _accept
    ServeCaps.reply = _reply
    _runtime.HttpRequest = HttpRequest
    _effects._PURE_VALUE_METHODS.update({"method", "path", "body", "body_bytes", "header"})
    _contracts.RESERVED_TYPE_PARAMETERS.add("HttpRequest")

    _ORIGINALS["check_method_call"] = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call
    _ORIGINALS["semantic_fallible"] = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINALS["method_type"] = _typed_ops.method_type
    _typed_ops.method_type = _method_type
    _typed_expr.method_type = _method_type

    _ORIGINALS["member"] = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member
    _ORIGINALS["invoke_member"] = _runtime.Interpreter._invoke_member
    _runtime.Interpreter._invoke_member = _invoke_member
    _ORIGINALS["facade_member_allowed"] = RuntimePrimitiveFacadeV1.__dict__["_member_allowed"]
    RuntimePrimitiveFacadeV1._member_allowed = classmethod(_facade_member_allowed)
    _ORIGINALS["runtime_matches"] = _runtime.Interpreter._runtime_matches_type
    _runtime.Interpreter._runtime_matches_type = _runtime_matches
    _INSTALLED = True


__all__ = ["HttpRequest", "REASONS", "install_serve_knowhere_v1", "request_method"]
