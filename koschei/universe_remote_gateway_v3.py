"""Koschei Universe Remote Observer Gateway v3.

Production-facing read-only mobile gateway. Adds a non-sensitive health endpoint
while retaining signed-envelope verification and a mutation-free browser surface.
"""
from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import time
from typing import Callable

from .universe_mobile_view_v1 import MOBILE_HTML_V1
from .universe_remote_observer_v1 import RemoteObserverEnvelopeV1, verify_remote_observer_v1


class RemoteGatewayV3Error(ValueError):
    pass


def _token_ok(expected: bytes, presented: str | None) -> bool:
    if not isinstance(expected, bytes) or len(expected) < 32 or not presented:
        return False
    prefix = "Bearer "
    if not presented.startswith(prefix):
        return False
    return hmac.compare_digest(presented[len(prefix):].encode("utf-8"), expected)


def _verified_json(envelope: RemoteObserverEnvelopeV1, *, signing_key: bytes, now_unix: int) -> bytes:
    if not verify_remote_observer_v1(envelope, signing_key=signing_key, now_unix=now_unix):
        raise RemoteGatewayV3Error("observer envelope verification failed or expired")
    value = asdict(envelope)
    if value.get("authority") is not False:
        raise RemoteGatewayV3Error("observer envelope must be authority-free")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def serve_remote_observer_v3(provider: Callable[[], RemoteObserverEnvelopeV1], *,
    bearer_token: bytes, signing_key: bytes, host: str = "127.0.0.1",
    port: int = 8876, now: Callable[[], int] | None = None) -> None:
    if not isinstance(bearer_token, bytes) or len(bearer_token) < 32:
        raise RemoteGatewayV3Error("bearer token must contain at least 256 bits")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise RemoteGatewayV3Error("observer signing key must contain at least 256 bits")
    if not (1 <= port <= 65535):
        raise RemoteGatewayV3Error("invalid port")
    clock = now or (lambda: int(time.time()))

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
            self.send_header("Content-Length", str(length))

        def _write(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code); self._headers(content_type, len(body)); self.end_headers()
            if body: self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._write(200, b'{"ok":true,"authority":false}', "application/json; charset=utf-8"); return
            if self.path == "/" or self.path.startswith("/?"):
                self._write(200, MOBILE_HTML_V1.encode("utf-8"), "text/html; charset=utf-8"); return
            if self.path != "/api/observer":
                self._write(404, b"", "text/plain; charset=utf-8"); return
            if not _token_ok(bearer_token, self.headers.get("Authorization")):
                self._write(401, b"", "text/plain; charset=utf-8"); return
            try:
                body = _verified_json(provider(), signing_key=signing_key, now_unix=clock())
            except RemoteGatewayV3Error:
                self._write(503, b"", "text/plain; charset=utf-8"); return
            self._write(200, body, "application/json; charset=utf-8")

        def do_POST(self): self._write(405, b"", "text/plain; charset=utf-8")
        def do_PUT(self): self._write(405, b"", "text/plain; charset=utf-8")
        def do_PATCH(self): self._write(405, b"", "text/plain; charset=utf-8")
        def do_DELETE(self): self._write(405, b"", "text/plain; charset=utf-8")
        def log_message(self, format, *args): return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
