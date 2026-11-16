"""Transport/authorization regressions; not evidence of live kernel isolation."""

import copy
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from koschei import playground_remote as remote
from koschei import untrusted
from server.playground import app, worker

TOKEN = "a" * 64
RESULT = {"action": "run", "stage": "run", "ran": True, "manifest": None,
          "policy": {"exit_code": 0, "stdout": "", "stderr": "", "timed_out": False},
          "run": {"exit_code": 0, "stdout": "hello\n", "stderr": "", "timed_out": False}}


@pytest.mark.parametrize("url", ["http://worker", "https://user:password@worker",
    "https://worker/api", "https://worker?source=x", "https://worker#x", "", "https://worker:bad"])
def test_endpoint_must_be_configured_https_origin(url):
    with pytest.raises(ValueError):
        remote.RemoteEvaluator(url, TOKEN)


@pytest.mark.parametrize("token", ["", "short", "x" * 64, "a" * 63, "a" * 64 + "\n"])
def test_worker_token_rejects_invalid_configuration(token):
    with pytest.raises(ValueError):
        remote.RemoteEvaluator("https://worker", token)


@pytest.fixture()
def transport(monkeypatch):
    class Response:
        status = 200
        content_type = "application/json; charset=utf-8"
        body = json.dumps(RESULT).encode()
        def getheader(self, name, default=""):
            return self.content_type
        def read(self, size):
            assert size == remote.MAX_RESPONSE_BYTES + 1
            return self.body[:size]
    class Connection:
        response = Response()
        closed = False
        request_args = None
        sock = None
        def __init__(self, host, port, timeout, context):
            assert (host, port, timeout) == ("worker.example", 443, 25)
            assert context.verify_mode == remote.ssl.CERT_REQUIRED and context.check_hostname
        def connect(self):
            pass
        def request(self, *args, **kwargs):
            Connection.request_args = (args, kwargs)
        def getresponse(self):
            return self.response
        def close(self):
            Connection.closed = True
    monkeypatch.setattr(remote.http.client, "HTTPSConnection", Connection)
    return Connection


def test_authenticated_transport_returns_valid_result_and_closes(transport):
    client = remote.RemoteEvaluator("https://worker.example", TOKEN)
    assert client.evaluate("fn main() {}", "run", "en") == RESULT
    args, kwargs = transport.request_args
    assert args == ("POST", "/api/evaluate")
    assert kwargs["headers"]["Authorization"] == "Bearer " + TOKEN
    assert json.loads(kwargs["body"])["source"] == "fn main() {}"
    assert transport.closed


@pytest.mark.parametrize("status", [301, 302, 307, 401, 503])
def test_worker_errors_and_redirects_fail_closed(transport, status):
    transport.response.status = status
    with pytest.raises(untrusted.SandboxUnavailable):
        remote.RemoteEvaluator("https://worker.example", TOKEN).evaluate("", "run", "en")
    assert transport.closed


@pytest.mark.parametrize("body", [b"[]", b"not json", b"x" * (remote.MAX_RESPONSE_BYTES + 1),
                                  b'{"action":"run","ran":true}', b'"scalar"'])
def test_invalid_and_oversized_worker_responses_are_rejected(transport, body):
    transport.response.body = body
    with pytest.raises(untrusted.SandboxUnavailable):
        remote.RemoteEvaluator("https://worker.example", TOKEN).evaluate("", "run", "en")
    assert transport.closed


def test_transport_timeout_is_sanitized(transport, monkeypatch):
    def timeout(self):
        raise TimeoutError("internal endpoint and secret " + TOKEN)
    monkeypatch.setattr(transport, "getresponse", timeout)
    with pytest.raises(untrusted.SandboxUnavailable) as caught:
        remote.RemoteEvaluator("https://worker.example", TOKEN).evaluate("", "run", "en")
    assert TOKEN not in str(caught.value)
    assert transport.closed


@pytest.mark.parametrize("changes", [{"stage": "check"}, {"action": "check"}, {"ran": "yes"},
    {"manifest": {"grants": [None]}}, {"manifest": {"required_domains": [7]}},
    {"run": {"exit_code": 0, "timed_out": False, "stdout": "x" * 20000, "stderr": ""}}])
def test_result_schema_rejects_inconsistent_or_unbounded_data(changes):
    result = copy.deepcopy(RESULT)
    result.update(changes)
    with pytest.raises(ValueError):
        remote.validate_result(result, "run")


@pytest.mark.parametrize("health", [{"ok": True}, {"ok": True, "evaluation_enabled": False, "protocol": 1},
                                   {"ok": True, "evaluation_enabled": True, "protocol": True}])
def test_remote_readiness_requires_protocol_and_execution(transport, health):
    transport.response.body = json.dumps(health).encode()
    with pytest.raises(untrusted.SandboxUnavailable):
        remote.RemoteEvaluator("https://worker.example", TOKEN).require_ready()


def test_remote_readiness_accepts_versioned_worker(transport):
    transport.response.body = b'{"ok":true,"evaluation_enabled":true,"protocol":1}'
    remote.RemoteEvaluator("https://worker.example", TOKEN).require_ready()


@pytest.fixture()
def running_worker(monkeypatch):
    monkeypatch.setattr(worker, "WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    calls = []
    def evaluate(*args):
        calls.append(args)
        return copy.deepcopy(RESULT)
    monkeypatch.setattr(app, "evaluate", evaluate)
    monkeypatch.setattr(app, "LIMITER", app.RateLimiter(100, 60))
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker.WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address, calls
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("authorizations", [[], ["Bearer wrong"], ["Bearer " + TOKEN, "Bearer " + TOKEN]])
def test_worker_authorizes_before_reading_source(running_worker, authorizations):
    address, calls = running_worker
    connection = http.client.HTTPConnection(*address, timeout=2)
    # Declare a body but do not send it: denial must not wait for it.
    connection.putrequest("POST", "/api/evaluate")
    connection.putheader("Content-Length", "100")
    for value in authorizations:
        connection.putheader("Authorization", value)
    connection.endheaders()
    assert connection.getresponse().status == 401
    connection.close()
    assert calls == []


def test_worker_secret_is_not_inherited_by_compiler(monkeypatch):
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("KOSCHEI_WORKER_URL", "https://worker.example")
    env = untrusted._child_env()
    assert "KOSCHEI_WORKER_TOKEN" not in env
    assert "KOSCHEI_WORKER_URL" not in env
    assert TOKEN not in env.values()


def test_worker_valid_request_and_no_website_routes(running_worker):
    address, calls = running_worker
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    for path, expected in (("/", 404), ("/health", 200)):
        connection = http.client.HTTPConnection(*address, timeout=2)
        connection.request("GET", path, headers=headers)
        assert connection.getresponse().status == expected
        connection.close()
    connection = http.client.HTTPConnection(*address, timeout=2)
    connection.request("POST", "/api/evaluate", json.dumps({"source": "fn main() {}"}), headers)
    response = connection.getresponse()
    assert response.status == 200 and json.load(response) == RESULT
    connection.close()
    assert len(calls) == 1


@pytest.mark.parametrize("sandbox,limits", [("off", "1"), ("bwrap", "0"), ("", "")])
def test_worker_rejects_weakened_configuration_before_listening(monkeypatch, sandbox, limits):
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", sandbox)
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", limits)
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    monkeypatch.setattr(worker, "ThreadingHTTPServer", lambda *a: pytest.fail("listener created"))
    with pytest.raises(untrusted.SandboxUnavailable):
        worker.main()


def test_worker_actual_admission_failure_prevents_listening(monkeypatch):
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "1")
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    monkeypatch.setattr(untrusted, "require_container_limits", lambda: None)
    def deny():
        raise untrusted.SandboxUnavailable("namespace denied")
    monkeypatch.setattr(untrusted, "require_sandbox_ready", deny)
    monkeypatch.setattr(worker, "ThreadingHTTPServer", lambda *a: pytest.fail("listener created"))
    with pytest.raises(untrusted.SandboxUnavailable):
        worker.main()


def test_frontend_never_falls_back_to_local_execution(monkeypatch):
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "remote")
    monkeypatch.setattr(untrusted, "evaluate", lambda *a: pytest.fail("local execution"))
    class FailedWorker:
        def evaluate(self, *args):
            raise untrusted.SandboxUnavailable("worker offline")
    monkeypatch.setattr(app, "REMOTE_WORKER", FailedWorker())
    with pytest.raises(untrusted.SandboxUnavailable):
        app.evaluate("", "run")


def test_real_https_rejects_untrusted_cert_then_accepts_trusted_worker(monkeypatch, tmp_path):
    import shutil
    import ssl
    import subprocess
    if shutil.which("openssl") is None:
        pytest.skip("OpenSSL is required for the local TLS integration test")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                   check=True, capture_output=True, timeout=15)
    monkeypatch.setattr(worker, "WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    monkeypatch.setattr(app, "evaluate", lambda *args: copy.deepcopy(RESULT))
    monkeypatch.setattr(app, "LIMITER", app.RateLimiter(100, 60))
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker.WorkerHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = remote.RemoteEvaluator(f"https://localhost:{server.server_port}", TOKEN)
        with pytest.raises(untrusted.SandboxUnavailable):
            client.require_ready()
        # Trust only this test certificate, retaining hostname verification.
        client = remote.RemoteEvaluator(f"https://localhost:{server.server_port}", TOKEN, ca_file=str(cert))
        client.require_ready()
        # The pinned certificate does not make another name acceptable.
        with pytest.raises(untrusted.SandboxUnavailable):
            remote.RemoteEvaluator(f"https://127.0.0.1:{server.server_port}", TOKEN, ca_file=str(cert)).require_ready()
        assert client.evaluate("fn main() {}", "run", "en") == RESULT
    finally:
        server.shutdown()
        server.server_close()


def test_frontend_remote_startup_waits_for_authenticated_readiness(monkeypatch):
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "remote")
    monkeypatch.setattr(app, "REMOTE_WORKER", None)
    events = []
    class Client:
        def require_ready(self):
            events.append("ready")
    candidate = Client()
    monkeypatch.setattr(app.RemoteEvaluator, "from_environment", lambda: candidate)
    monkeypatch.setattr(untrusted, "require_sandbox_ready", lambda: pytest.fail("local sandbox used"))
    class Server:
        def __init__(self, *args):
            assert app.REMOTE_WORKER is candidate
            events.append("listen")
        def serve_forever(self):
            pass
    monkeypatch.setattr(app, "ThreadingHTTPServer", Server)
    app.main()
    assert events == ["ready", "listen"]


def test_frontend_offline_worker_keeps_site_up_with_evaluation_disabled(monkeypatch):
    """An offline worker must not take the website down, nor enable local runs."""
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "remote")
    monkeypatch.setattr(app, "REMOTE_WORKER", None)
    class Client:
        def require_ready(self):
            raise untrusted.SandboxUnavailable("offline")
    candidate = Client()
    monkeypatch.setattr(app.RemoteEvaluator, "from_environment", lambda: candidate)
    monkeypatch.setattr(untrusted, "evaluate", lambda *a: pytest.fail("local execution"))
    watchers = []
    class Thread:
        def __init__(self, target, args, daemon):
            assert target is app.watch_remote_worker and args == (candidate,) and daemon
            watchers.append(self)
        def start(self):
            pass
    monkeypatch.setattr(app.threading, "Thread", Thread)
    listened = []
    class Server:
        def __init__(self, *args):
            listened.append(args)
        def serve_forever(self):
            pass
    monkeypatch.setattr(app, "ThreadingHTTPServer", Server)
    app.main()
    assert listened and len(watchers) == 1
    assert app.REMOTE_WORKER is None and app.evaluation_enabled() is False
    with pytest.raises(untrusted.SandboxUnavailable):
        app.evaluate("", "run")


def test_remote_watcher_enables_evaluation_only_after_readiness(monkeypatch):
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "remote")
    monkeypatch.setattr(app, "REMOTE_WORKER", None)
    monkeypatch.setattr(app, "REMOTE_READINESS_RETRY_SECONDS", 0)
    attempts = []
    class Client:
        def require_ready(self):
            attempts.append(1)
            if len(attempts) < 3:
                raise untrusted.SandboxUnavailable("not yet")
    client = Client()
    app.watch_remote_worker(client)
    assert len(attempts) == 3 and app.REMOTE_WORKER is client and app.evaluation_enabled()


def test_bad_remote_configuration_still_stops_startup(monkeypatch):
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "remote")
    monkeypatch.setenv("KOSCHEI_WORKER_URL", "http://not-https")
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(app, "ThreadingHTTPServer", lambda *a: pytest.fail("listener created"))
    with pytest.raises(ValueError):
        app.main()


def _tls_files(tmp_path):
    import shutil
    import subprocess
    if shutil.which("openssl") is None:
        pytest.skip("OpenSSL is required for the local TLS integration test")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                   check=True, capture_output=True, timeout=15)
    return cert, key


def test_dripping_worker_is_cut_at_the_total_deadline(monkeypatch, tmp_path):
    """Each byte arrives well inside the socket timeout; the total must still end."""
    import socket
    import ssl
    import time
    cert, key = _tls_files(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    stop = threading.Event()

    def serve():
        raw, _ = listener.accept()
        with context.wrap_socket(raw, server_side=True) as tls:
            tls.recv(65536)
            head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100000\r\n\r\n"
            tls.sendall(head)
            while not stop.is_set():
                try:
                    tls.sendall(b" ")
                except OSError:
                    return
                time.sleep(0.2)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    monkeypatch.setattr(remote, "REQUEST_DEADLINE_SECONDS", 1.5)
    client = remote.RemoteEvaluator(f"https://localhost:{listener.getsockname()[1]}", TOKEN, ca_file=str(cert))
    started = time.monotonic()
    try:
        with pytest.raises(untrusted.SandboxUnavailable):
            client.require_ready()
        assert time.monotonic() - started < 4
    finally:
        stop.set()
        listener.close()


def test_hanging_dns_is_cut_at_the_total_deadline(monkeypatch):
    import socket
    import time
    release = threading.Event()

    def stuck(*args, **kwargs):
        release.wait(10)
        raise socket.gaierror("released")

    monkeypatch.setattr(socket, "getaddrinfo", stuck)
    monkeypatch.setattr(remote, "REQUEST_DEADLINE_SECONDS", 1)
    started = time.monotonic()
    try:
        with pytest.raises(untrusted.SandboxUnavailable):
            remote.RemoteEvaluator("https://worker.invalid", TOKEN).require_ready()
        assert time.monotonic() - started < 3
    finally:
        release.set()


def test_slow_client_is_cut_at_the_read_deadline_and_others_are_served(monkeypatch):
    import socket
    import time
    monkeypatch.setattr(app, "REQUEST_READ_DEADLINE_SECONDS", 1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        slow = socket.create_connection(server.server_address, timeout=5)
        slow.sendall(b"GET /health HTTP/1.1\r\n")
        started = time.monotonic()
        closed = False
        while time.monotonic() - started < 4:
            try:
                slow.sendall(b"X-Drip: 1\r\n")
            except OSError:
                closed = True
                break
            # The healthy client is served while the slow one is pending.
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            connection.request("GET", "/health")
            assert connection.getresponse().status == 200
            connection.close()
            time.sleep(0.3)
            try:
                slow.settimeout(0.01)
                if slow.recv(1) == b"":
                    closed = True
                    break
            except (socket.timeout, BlockingIOError):
                pass
            except OSError:
                closed = True
                break
        assert closed and time.monotonic() - started < 3
        slow.close()
    finally:
        server.shutdown()
        server.server_close()


def test_stalled_tls_handshake_does_not_block_the_worker(monkeypatch, tmp_path):
    import socket
    import ssl
    cert, key = _tls_files(tmp_path)
    monkeypatch.setattr(worker, "WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(app, "REQUEST_READ_DEADLINE_SECONDS", 2)
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker.WorkerHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        stalled = socket.create_connection(server.server_address, timeout=5)  # never says hello
        client = remote.RemoteEvaluator(f"https://localhost:{server.server_port}", TOKEN, ca_file=str(cert))
        client.require_ready()
        stalled.close()
    finally:
        server.shutdown()
        server.server_close()
