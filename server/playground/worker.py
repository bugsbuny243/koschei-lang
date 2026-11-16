"""Private execution worker for the Koschei Playground.

Start with `python worker.py` under the systemd unit in server/playground/vm.
Authentication and real confinement are mandatory: the worker refuses to listen
unless the live process passes the seccomp/no-new-privileges/cgroup and
namespace preflights. It serves HTTPS itself (certificate and key from the
systemd credential directory or explicit paths); plain HTTP is only allowed on
a loopback bind for local tests.
"""

import hmac
import ipaddress
import os
import ssl
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path

from koschei import untrusted
from koschei.playground_remote import worker_token

if __package__:
    from . import app
else:
    import app


WORKER_TOKEN = ""


def _secret(name: str, env: str) -> str:
    """An operator secret: systemd credential first, then the environment."""
    directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if directory:
        path = Path(directory) / name
        if path.is_file():
            return path.read_text(encoding="ascii").strip()
    return os.environ.get(env, "")


def _credential_path(name: str, env: str) -> str:
    directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if directory and (Path(directory) / name).is_file():
        return str(Path(directory) / name)
    return os.environ.get(env, "")


class WorkerHandler(app.Handler):
    rate_limited = False

    def setup(self):
        super().setup()
        # The TLS handshake runs here, in the connection's own thread and
        # under the request read deadline, never in the accept loop.
        if isinstance(self.connection, ssl.SSLSocket):
            self.connection.do_handshake()

    def _authenticated(self) -> bool:
        values = self.headers.get_all("Authorization", [])
        expected = ("Bearer " + WORKER_TOKEN).encode("ascii")
        if (not WORKER_TOKEN or len(values) != 1
                or not hmac.compare_digest(values[0].encode("utf-8"), expected)):
            self._request_read()
            self.close_connection = True
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if not self._authenticated():
            return
        self._request_read()
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "evaluation_enabled": True, "protocol": 1})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    do_HEAD = do_GET

    def do_POST(self):
        if self._authenticated():
            super().do_POST()

    def log_message(self, fmt, *args):
        # Do not log request targets, headers or source on this private endpoint.
        pass


def tls_context() -> ssl.SSLContext | None:
    cert = _credential_path("tls-cert", "KOSCHEI_WORKER_TLS_CERT")
    key = _credential_path("tls-key", "KOSCHEI_WORKER_TLS_KEY")
    if not cert and not key:
        return None
    if not cert or not key:
        raise untrusted.SandboxUnavailable("Worker TLS needs both a certificate and a key")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return context


def main():
    global WORKER_TOKEN
    WORKER_TOKEN = worker_token(_secret("worker-token", "KOSCHEI_WORKER_TOKEN"))
    if (app.PLAYGROUND_MODE != "enabled"
            or os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX") != "bwrap"
            or os.environ.get("KOSCHEI_REQUIRE_CONTAINER_LIMITS") != "1"):
        raise untrusted.SandboxUnavailable("Worker requires enabled mode and mandatory confinement")
    bind = os.environ.get("KOSCHEI_WORKER_BIND", "127.0.0.1")
    context = tls_context()
    if context is None and not ipaddress.ip_address(bind).is_loopback:
        raise untrusted.SandboxUnavailable("A non-loopback worker must serve TLS")
    untrusted.require_container_limits()
    untrusted.require_sandbox_ready()
    server = ThreadingHTTPServer((bind, int(os.environ.get("PORT", "8081"))), WorkerHandler)
    if context is not None:
        server.socket = context.wrap_socket(server.socket, server_side=True,
                                            do_handshake_on_connect=False)
    server.serve_forever()


if __name__ == "__main__":
    main()
