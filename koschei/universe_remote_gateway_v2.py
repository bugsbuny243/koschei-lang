"""Koschei Universe Remote Observer Gateway v2.

Serves the touch-first mobile Universe view at `/` and only a freshly verified,
authority-free observer envelope at `/api/observer`. Mutation methods are denied.
The gateway is not a control plane and never exports its signing key.
"""
from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import time
from typing import Callable

from .universe_mobile_view_v1 import MOBILE_HTML_V1
from .universe_remote_observer_v1 import (
    RemoteObserverEnvelopeV1,
    verify_remote_observer_v1,
)


class RemoteGatewayV2Error(ValueError):
    pass


def _token_ok(expected: bytes, presented: str | None) -> bool:
    if not isinstance(expected, bytes) or len(expected) < 32 or not presented:
        return False
    prefix = "Bearer "
    if not presented.startswith(prefix):
        return False
    return hmac.compare_digest(presented[len(prefix):].encode("utf-8"), expected)


def verified_envelope_json_v2(*, envelope: RemoteObserverEnvelopeV1,
    signing_key: bytes, now_unix: int) -> bytes:
    if not verify_remote_observer_v1(envelope, signing_key=signing_key, now_unix=now_unix):
        raise RemoteGatewayV2Error("observer envelope verification failed or expired")
    value = asdict(envelope)
    if value.get("authority") is not False:
        raise RemoteGatewayV2Error("observer envelope must be authority-free")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def serve_remote_observer_v2(provider: Callable[[], RemoteObserverEnvelopeV1], *,
    bearer_token: bytes, signing_key: bytes, host: str = "127.0.0.1",
    port: int = 8876, now: Callable[[], int] | None = None) -> None:
    """Serve the mobile observer UI and verified snapshots.

    Binding beyond loopback is deployment policy, not implicit permission. Public
    deployment must terminate HTTPS in front of this process and protect access
    independently. This server itself carries no Koschei execution authority.
    """
    if not isinstance(bearer_token, bytes) or len(bearer_token) < 32:
        raise RemoteGatewayV2Error("bearer token must contain at least 256 bits")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise RemoteGatewayV2Error("observer signing key must contain at least 256 bits")
    if not (1 <= port <= 65535):
        raise RemoteGatewayV2Error("invalid port")
    clock = now or (lambda: int(time.time()))

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
            self.send_header("Content-Length", str(length))

        def _deny(self, code: int) -> None:
            self.send_response(code)
            self._headers("text/plain; charset=utf-8", 0)
            self.end_headers()

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                body = MOBILE_HTML_V1.encode("utf-8")
                self.send_response(200)
                self._headers("text/html; charset=utf-8", len(body))
                self.end_headers(); self.wfile.write(body); return
            if self.path != "/api/observer":
                self._deny(404); return
            if not _token_ok(bearer_token, self.headers.get("Authorization")):
                self._deny(401); return
            try:
                body = verified_envelope_json_v2(
                    envelope=provider(), signing_key=signing_key, now_unix=clock()
                )
            except RemoteGatewayV2Error:
                self._deny(503); return
            self.send_response(200)
            self._headers("application/json; charset=utf-8", len(body))
            self.end_headers(); self.wfile.write(body)

        def do_POST(self): self._deny(405)
        def do_PUT(self): self._deny(405)
        def do_PATCH(self): self._deny(405)
        def do_DELETE(self): self._deny(405)
        def log_message(self, format, *args): return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
