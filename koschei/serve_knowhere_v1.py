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
``HttpRequest`` value. ``reply(status, body)`` answers that request as
``text/plain; charset=utf-8`` and closes its connection;
``reply_as(status, content_type, body)`` names the content type, checked by
``net_v1.valid_content_type``.

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

**Reads run beside the program.** Once the listener is open, connections are
accepted and their requests read concurrently, up to
``min(max_connections, 128)`` at a time; ``accept()`` returns the next request
that has arrived in full, the earliest-accepted first. A client that
connects and sends nothing occupies one reader until its deadline instead of
the server: the program still answers one request at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import threading
import time
from typing import Any

from . import effect_contracts_v1 as _effects
from . import interpreter as _runtime
from . import net_v1
from . import semantic as _semantic
from . import serve_loopback_exchange_v1 as _exchange
from . import type_contracts as _contracts
from . import _typed_expr
from . import _typed_ops
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .serve_authority_v1 import ServeCaps, _parse_loopback_bind
from .type_system import ERROR, STRING, GenericType, NamedType, VOID, union_type

HTTP_REQUEST = NamedType("HttpRequest")
REQUEST_METHODS = {"method": 0, "path": 0, "body": 0, "body_bytes": 0, "header": 1}

PENDING_MESSAGE = "KS3470: Önceki istek yanıtlanmadan yeni istek kabul edilemez; önceki istek 500 ile kapatıldı."
NO_PENDING_MESSAGE = "KS3470: Yanıtlanacak bekleyen bir istek yok."
BUDGET_MESSAGE = "KS3471: Sunucunun istek bütçesi tükendi: en fazla {count} istek kabul edilebilir."
STATUS_MESSAGE = "KS3472: Desteklenmeyen HTTP durum kodu: {status}."
EMPTY_BODY_MESSAGE = "KS3472: 204 yanıtı gövde taşıyamaz."
CONTENT_TYPE_MESSAGE = (
    f"KS3472: Yanıtın içerik türü 1-{net_v1.CONTENT_TYPE_MAX_BYTES} yazdırılabilir ASCII "
    "karakter olmalı ve iki ucunda boşluk olmamalı."
)
PLAIN_TEXT = "text/plain; charset=utf-8"
# reply_with(status, headers, body): the program's own response headers.
MAX_RESPONSE_HEADERS = 32
MAX_HEADER_NAME_BYTES = 64
MAX_HEADER_VALUE_BYTES = 4096
# The server frames every response itself, so these are never the program's.
RESERVED_RESPONSE_HEADERS = (
    "connection", "content-length", "keep-alive", "proxy-connection", "te", "trailer",
    "transfer-encoding", "upgrade",
)
HEADERS_MESSAGE = (
    f"KS3472: Yanıt başlıkları geçersiz: en fazla {MAX_RESPONSE_HEADERS} başlık; her ad "
    f"1-{MAX_HEADER_NAME_BYTES} baytlık bir HTTP token'ı ve bir kez; değer "
    f"1-{MAX_HEADER_VALUE_BYTES} yazdırılabilir ASCII karakter, iki ucunda boşluk yok; "
    "Connection, Content-Length, Keep-Alive, Proxy-Connection, TE, Trailer, "
    "Transfer-Encoding ve Upgrade sunucunundur."
)
_TOKEN_CHARACTERS = frozenset(
    "!#$%&'*+-.^_`|~0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


def response_headers(pairs: list[tuple[Any, Any]]) -> tuple[str, list[tuple[str, str]]] | str:
    """(content type, other headers) for a reply, or the Error text.

    The native broker ports this check in the same order.
    """

    if len(pairs) > MAX_RESPONSE_HEADERS:
        return HEADERS_MESSAGE
    content_type = PLAIN_TEXT
    extra: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in pairs:
        if (
            not isinstance(name, str)
            or not 0 < len(name) <= MAX_HEADER_NAME_BYTES
            or any(character not in _TOKEN_CHARACTERS for character in name)
        ):
            return HEADERS_MESSAGE
        folded = name.translate(_ASCII_LOWER)
        if folded in seen:
            return HEADERS_MESSAGE
        seen.add(folded)
        if folded == "content-type":
            if not net_v1.valid_content_type(value):
                return CONTENT_TYPE_MESSAGE
            content_type = value
            continue
        if folded in RESERVED_RESPONSE_HEADERS:
            return HEADERS_MESSAGE
        if (
            not isinstance(value, str)
            or not 0 < len(value) <= MAX_HEADER_VALUE_BYTES
            or any(not "\x20" <= character <= "\x7e" for character in value)
            or value[0] == " "
            or value[-1] == " "
        ):
            return HEADERS_MESSAGE
        extra.append((name, value))
    return content_type, extra
HEADER_MESSAGE = "KS3473: İstekte '{name}' başlığı yok."
BODY_TEXT_MESSAGE = "KS3430: İstek gövdesi geçerli UTF-8 metin değil."

REASONS = {
    200: "OK", 201: "Created", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 303: "See Other", 307: "Temporary Redirect",
    308: "Permanent Redirect", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 409: "Conflict", 413: "Content Too Large",
    422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error",
    503: "Service Unavailable",
}

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")

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
    """The listener, the one pending request and the requests read so far.

    A background thread accepts connections and starts one reader per
    connection; at most ``slots`` connections are being read or waiting in
    ``ready`` at once, and no more than ``max_connections`` are ever accepted.
    """

    __slots__ = (
        "listener", "pending", "accepted", "ready", "reading", "condition",
        "slots", "closed", "connections", "caps_policy",
    )

    def __init__(self, listener: socket.socket, policy) -> None:
        self.listener = listener
        self.pending: socket.socket | None = None
        self.accepted = 0
        # (sequence, connection, HttpRequest) or (sequence, None, KsError).
        self.ready: list = []
        self.reading = 0
        self.condition = threading.Condition()
        self.slots = threading.BoundedSemaphore(min(policy.max_connections, MAX_CONCURRENT_READS))
        self.closed = False
        self.connections: set[socket.socket] = set()
        self.caps_policy = policy

    def start(self) -> None:
        threading.Thread(target=self._accept_loop, name="koschei-serve-accept", daemon=True).start()

    def _accept_loop(self) -> None:
        policy = self.caps_policy
        while True:
            self.slots.acquire()
            with self.condition:
                if self.closed or self.accepted >= policy.max_connections:
                    self.slots.release()
                    self.condition.notify_all()
                    return
            try:
                connection, _peer = self.listener.accept()
            except OSError as error:
                with self.condition:
                    if self.closed:
                        self.slots.release()
                        return
                    # The Error value holds the slot until accept() takes it.
                    self.ready.append((self.accepted + 1, None, _exchange._io_error(f"accept failed: {_exchange.socket_code(error)}")))
                    self.condition.notify_all()
                # A listener that cannot accept will not recover.
                return
            with self.condition:
                if self.closed:
                    _close(connection)
                    self.slots.release()
                    return
                self.accepted += 1
                sequence = self.accepted
                self.reading += 1
                self.connections.add(connection)
            threading.Thread(target=self._read, args=(sequence, connection), name="koschei-serve-read", daemon=True).start()

    def _read(self, sequence: int, connection: socket.socket) -> None:
        deadline = time.monotonic() + self.caps_policy.deadline_ms / 1000.0
        request, failure = _read_request(connection, self.caps_policy, deadline)
        if failure is not None:
            status, error = failure
            _close(connection, status, deadline)
        with self.condition:
            self.reading -= 1
            if failure is not None:
                # The client was answered; its Error value holds the slot
                # until accept() hands it to the program.
                self.connections.discard(connection)
                if self.closed:
                    self.slots.release()
                else:
                    self.ready.append((sequence, None, error))
            elif self.closed:
                self.connections.discard(connection)
                self.slots.release()
                _close(connection)
            else:
                self.ready.append((sequence, connection, request))
            self.condition.notify_all()

    def take(self, wait_seconds: float):
        """The next read request, or None after waiting at most wait_seconds."""
        deadline = time.monotonic() + wait_seconds
        with self.condition:
            while not self.ready:
                exhausted = self.accepted >= self.caps_policy.max_connections and self.reading == 0
                if exhausted:
                    return BUDGET
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.condition.wait(remaining)
            earliest = min(range(len(self.ready)), key=lambda index: self.ready[index][0])
            _sequence, connection, item = self.ready.pop(earliest)
            if connection is not None:
                self.connections.discard(connection)
            self.slots.release()
            return connection, item

    def close(self) -> None:
        with self.condition:
            if self.closed:
                return
            self.closed = True
            open_connections = list(self.connections)
            self.connections.clear()
            queued = [connection for _, connection, _ in self.ready if connection is not None]
            for _ in self.ready:
                self.slots.release()
            self.ready.clear()
            self.condition.notify_all()
        try:
            # close() alone does not wake a thread blocked in accept(), and
            # the kernel keeps listening for it; shutdown() does.
            self.listener.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.listener.close()
        except OSError:
            pass
        for connection in open_connections + queued:
            _close(connection)
        if self.pending is not None:
            _close(self.pending)
            self.pending = None


# Requests read at once, per server; also the most that wait for accept().
MAX_CONCURRENT_READS = 128
BUDGET = object()


def _wire(
    status: int, body: bytes, content_type: str = PLAIN_TEXT, extra: tuple[tuple[str, str], ...] = ()
) -> bytes:
    head = (
        f"HTTP/1.1 {status} {REASONS[status]}\r\n"
        f"Content-Type: {content_type}\r\n"
        + "".join(f"{name}: {value}\r\n" for name, value in extra)
        + f"Content-Length: {len(body)}\r\n"
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
        return _exchange._io_error(f"listener failed: {_exchange.socket_code(error)}")
    server = _Server(listener, caps.policy)
    server.start()
    return server


def _parse_headers(raw_head: bytes) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    lines = raw_head.decode("iso-8859-1").split("\r\n")
    method, target, _version = lines[0].split(" ")
    headers = []
    for line in lines[1:]:
        name, value = line.split(":", 1)
        headers.append((name.lower(), value.strip(" \t")))
    return method, target, tuple(headers)


def _read_request(connection: socket.socket, policy, deadline: float):
    """(HttpRequest, None) or (None, (status, KsError))."""

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
        return None, (400, _exchange._io_error(f"request read failed: {_exchange.socket_code(error)}"))
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
    taken = server.take(self.policy.deadline_ms / 1000.0)
    if taken is BUDGET:
        return _runtime.KsError(BUDGET_MESSAGE.format(count=self.policy.max_connections))
    if taken is None:
        return _exchange._io_error("accept exceeded the I/O deadline")
    connection, item = taken
    if connection is None:
        return item
    server.pending = connection
    return item


def _reply(self: ServeCaps, status: Any, body: Any):
    return _respond(self, status, [("Content-Type", PLAIN_TEXT)], body)


def _reply_as(self: ServeCaps, status: Any, content_type: Any, body: Any):
    return _respond(self, status, [("Content-Type", content_type)], body)


def _reply_with(self: ServeCaps, status: Any, headers: Any, body: Any):
    pairs = list(headers.items()) if isinstance(headers, dict) else [(None, None)]
    return _respond(self, status, pairs, body)


def _respond(self: ServeCaps, status: Any, headers: list[tuple[Any, Any]], body: Any):
    server = self._server
    if server is None or server.pending is None:
        return _runtime.KsError(NO_PENDING_MESSAGE)
    connection = server.pending
    server.pending = None
    if type(status) is not int or status not in REASONS:
        _close(connection, 500)
        return _runtime.KsError(STATUS_MESSAGE.format(status=status))
    checked = response_headers(headers)
    if isinstance(checked, str):
        _close(connection, 500)
        return _runtime.KsError(checked)
    content_type, extra = checked
    if not isinstance(body, (str, bytes)):
        _close(connection, 500)
        return _exchange._protocol_error("ServeCaps.reply() body must be String or Bytes")
    payload = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    if status == 204 and payload:
        _close(connection, 500)
        return _runtime.KsError(EMPTY_BODY_MESSAGE)
    wire = _wire(status, payload, content_type, tuple(extra))
    if len(wire) > self.policy.max_response_bytes:
        _close(connection, 500)
        return _exchange._protocol_error("response exceeds max_response_bytes")
    try:
        connection.settimeout(self.policy.deadline_ms / 1000.0)
        connection.sendall(wire)
    except (socket.timeout, TimeoutError):
        return _exchange._io_error("response write exceeded the I/O deadline")
    except OSError as error:
        return _exchange._io_error(f"response write failed: {_exchange.socket_code(error)}")
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
        # Names are ASCII tokens (serve_loopback_exchange_v1), so only ASCII
        # letters fold.
        folded = wanted.translate(_ASCII_LOWER)
        for header, value in request.headers:
            if header == folded:
                return value
        return _runtime.KsError(HEADER_MESSAGE.format(name=wanted))
    raise AssertionError(name)


# ---- checking ---------------------------------------------------------------


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    values = argument_types or []
    if receiver_type == "ServeCaps" and method_name in {"accept", "reply", "reply_as", "reply_with"}:
        expected = {"accept": 0, "reply": 2, "reply_as": 3, "reply_with": 3}[method_name]
        if len(values) != expected:
            raise _semantic.SemanticError(
                "KS1301", f"ServeCaps.{method_name}() {expected} argüman bekler, {len(values)} verildi.", location
            )
        if method_name != "accept":
            subject = f"ServeCaps.{method_name}()"
            self._require_assignable(("Int",), values[0], f"{subject} durum kodu", location)
            if method_name == "reply_as":
                self._require_assignable(("String",), values[1], f"{subject} içerik türü", location)
            if method_name == "reply_with":
                self._require_assignable(("Map", "Map<String, String>"), values[1], f"{subject} başlıkları", location)
            self._require_assignable(("String", "Bytes"), values[-1], f"{subject} gövdesi", location)
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


_HEADER_MAP = GenericType("Map", (STRING, STRING))

_TYPED = {
    ("ServeCaps", "accept"): (0, union_type(HTTP_REQUEST, ERROR)),
    ("ServeCaps", "reply"): (2, union_type(VOID, ERROR)),
    ("ServeCaps", "reply_as"): (3, union_type(VOID, ERROR)),
    ("ServeCaps", "reply_with"): (3, union_type(VOID, ERROR)),
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
            if (receiver.name, method) == ("ServeCaps", "reply_with") and arguments[1] != _HEADER_MAP:
                raise _semantic.SemanticError(
                    "KS1301", "ServeCaps.reply_with() başlıkları Map<String, String> olmalıdır.", location
                )
            return result
        if receiver.name == "HttpRequest":
            raise _semantic.SemanticError(
                "KS1306", f"'{method}' işlemi HttpRequest tipi için güvenli değildir.", location
            )
    return _ORIGINALS["method_type"](receiver, method, arguments, location)


# ---- runtimes ---------------------------------------------------------------


def _member(self, receiver, name, location):
    if isinstance(receiver, ServeCaps) and name in {"accept", "reply", "reply_as", "reply_with"}:
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
    ServeCaps.reply_as = _reply_as
    ServeCaps.reply_with = _reply_with
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
