"""Private execution worker. Terminate TLS at a private, trusted ingress.

Start with `python worker.py`; authentication and real confinement are mandatory.
Never expose the plain HTTP listener directly to the public Internet.
"""

import hmac
import os
from http import HTTPStatus
from http.server import ThreadingHTTPServer

from koschei import untrusted
from koschei.playground_remote import worker_token

if __package__:
    from . import app
else:
    import app


WORKER_TOKEN = ""


class WorkerHandler(app.Handler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def _authenticated(self) -> bool:
        values = self.headers.get_all("Authorization", [])
        expected = ("Bearer " + WORKER_TOKEN).encode("ascii")
        if (not WORKER_TOKEN or len(values) != 1
                or not hmac.compare_digest(values[0].encode("utf-8"), expected)):
            self.close_connection = True
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if not self._authenticated():
            return
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


def main():
    global WORKER_TOKEN
    WORKER_TOKEN = worker_token(os.environ.get("KOSCHEI_WORKER_TOKEN", ""))
    if (app.PLAYGROUND_MODE != "enabled"
            or os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX") != "bwrap"
            or os.environ.get("KOSCHEI_REQUIRE_CONTAINER_LIMITS") != "1"):
        raise untrusted.SandboxUnavailable("Worker requires enabled mode and mandatory confinement")
    untrusted.require_container_limits()
    untrusted.require_sandbox_ready()
    ThreadingHTTPServer((os.environ.get("KOSCHEI_WORKER_BIND", "127.0.0.1"),
                         int(os.environ.get("PORT", "8081"))), WorkerHandler).serve_forever()


if __name__ == "__main__":
    main()
