"""Koschei Universe Remote Observer Gateway v1.

Read-only HTTP gateway for mobile/remote observers. It serves only short-lived,
authority-free observer envelopes and never accepts mutation requests.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from typing import Callable


class RemoteGatewayError(ValueError):
    pass


def _token_ok(expected: bytes, presented: str | None) -> bool:
    if not expected or presented is None:
        return False
    prefix = "Bearer "
    if not presented.startswith(prefix):
        return False
    try:
        candidate = presented[len(prefix):].encode("utf-8")
    except Exception:
        return False
    return hmac.compare_digest(candidate, expected)


def envelope_json_v1(envelope: object) -> bytes:
    if is_dataclass(envelope):
        value = asdict(envelope)
    elif isinstance(envelope, dict):
        value = dict(envelope)
    else:
        raise RemoteGatewayError("observer envelope must be a dataclass or dict")
    if value.get("authority") not in (False, None):
        raise RemoteGatewayError("remote observer payload must be authority-free")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=lambda v: v.hex() if isinstance(v, bytes) else str(v)).encode("utf-8")


def serve_remote_observer_v1(provider: Callable[[], object], *,
    bearer_token: bytes, host: str = "127.0.0.1", port: int = 8876) -> None:
    """Serve signed/short-lived observer envelopes over a token-gated read-only API.

    TLS/edge termination is intentionally outside this primitive. Deployments that
    bind beyond loopback must place it behind an authenticated HTTPS reverse proxy.
    """
    if not isinstance(bearer_token, bytes) or len(bearer_token) < 32:
        raise RemoteGatewayError("bearer token must contain at least 256 bits")
    if not (1 <= port <= 65535):
        raise RemoteGatewayError("invalid port")

    class Handler(BaseHTTPRequestHandler):
        def _deny(self, code: int) -> None:
            self.send_response(code)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path != "/api/observer":
                self._deny(404); return
            if not _token_ok(bearer_token, self.headers.get("Authorization")):
                self._deny(401); return
            body = envelope_json_v1(provider())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_POST(self): self._deny(405)
        def do_PUT(self): self._deny(405)
        def do_PATCH(self): self._deny(405)
        def do_DELETE(self): self._deny(405)
        def log_message(self, format, *args): return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
