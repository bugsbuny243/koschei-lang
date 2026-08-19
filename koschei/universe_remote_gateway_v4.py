"""Koschei Universe Remote Observer Gateway v4.

Public mobile gateway with a human login that exchanges a high-entropy bootstrap
secret for a short-lived, HttpOnly, read-only observer session. Long-lived
observer/signing secrets never enter browser JavaScript.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
from hashlib import sha256
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import time
from typing import Callable
from urllib.parse import parse_qs

from .universe_mobile_view_v2 import MOBILE_HTML_V2
from .universe_remote_observer_v1 import RemoteObserverEnvelopeV1, verify_remote_observer_v1

_COOKIE = "koschei_observer_session"

class RemoteGatewayV4Error(ValueError):
    pass


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session_v4(*, session_key: bytes, now_unix: int, ttl_seconds: int) -> str:
    if len(session_key) < 32 or not 60 <= ttl_seconds <= 86400:
        raise RemoteGatewayV4Error("invalid session policy")
    body = f"{now_unix + ttl_seconds}:{secrets.token_hex(16)}".encode("ascii")
    sig = hmac.new(session_key, b"koschei.universe.session/v4\x00" + body, sha256).digest()
    return _b64e(body + b"." + sig)


def verify_session_v4(token: str, *, session_key: bytes, now_unix: int) -> bool:
    try:
        raw = _b64d(token)
        body, sig = raw.rsplit(b".", 1)
        exp_raw, _nonce = body.split(b":", 1)
        exp = int(exp_raw)
    except Exception:
        return False
    expected = hmac.new(session_key, b"koschei.universe.session/v4\x00" + body, sha256).digest()
    return hmac.compare_digest(sig, expected) and now_unix <= exp


def _verified_json(envelope: RemoteObserverEnvelopeV1, *, signing_key: bytes, now_unix: int) -> bytes:
    if not verify_remote_observer_v1(envelope, signing_key=signing_key, now_unix=now_unix):
        raise RemoteGatewayV4Error("observer envelope verification failed or expired")
    value = asdict(envelope)
    if value.get("authority") is not False:
        raise RemoteGatewayV4Error("observer envelope must be authority-free")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _login_html(error: bool = False) -> bytes:
    msg = '<p class="bad">access code rejected</p>' if error else '<p>read-only observer access</p>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Koschei Universe Access</title><style>html,body{{margin:0;min-height:100%;background:#02050d;color:#eaf2ff;font-family:ui-monospace,monospace}}main{{max-width:520px;margin:16vh auto;padding:24px}}section{{border:1px solid #234767;background:#07101ddd;border-radius:18px;padding:22px}}h1{{letter-spacing:.13em;font-size:24px}}p{{opacity:.8}}input,button{{box-sizing:border-box;width:100%;padding:14px;border-radius:12px;font:inherit}}input{{background:#030914;color:#fff;border:1px solid #31597b;margin:14px 0}}button{{background:#dcecff;color:#03101c;border:0;font-weight:700}}.bad{{color:#ff7187}}</style></head><body><main><section><h1>KOSCHEI UNIVERSE</h1>{msg}<form method="post" action="/session"><input name="password" type="password" autocomplete="current-password" placeholder="observer access code" required><button type="submit">ENTER UNIVERSE</button></form></section></main></body></html>'''.encode("utf-8")


def serve_remote_observer_v4(provider: Callable[[], RemoteObserverEnvelopeV1], *,
    login_hash: bytes, session_key: bytes, signing_key: bytes,
    host: str = "127.0.0.1", port: int = 8876,
    session_ttl_seconds: int = 1800, now: Callable[[], int] | None = None) -> None:
    if len(login_hash) != 32:
        raise RemoteGatewayV4Error("login hash must be SHA-256 bytes")
    if len(session_key) < 32 or len(signing_key) < 32:
        raise RemoteGatewayV4Error("session/signing keys must contain at least 256 bits")
    if not 60 <= session_ttl_seconds <= 86400 or not 1 <= port <= 65535:
        raise RemoteGatewayV4Error("invalid gateway policy")
    clock = now or (lambda: int(time.time()))

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, content_type: str, length: int, *, cookie: str | None = None, location: str | None = None) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            if cookie: self.send_header("Set-Cookie", cookie)
            if location: self.send_header("Location", location)
            self.send_header("Content-Length", str(length))

        def _write(self, code: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8", *, cookie: str | None = None, location: str | None = None) -> None:
            self.send_response(code); self._headers(content_type, len(body), cookie=cookie, location=location); self.end_headers()
            if body: self.wfile.write(body)

        def _session_ok(self) -> bool:
            jar = SimpleCookie(); jar.load(self.headers.get("Cookie", ""))
            morsel = jar.get(_COOKIE)
            return bool(morsel and verify_session_v4(morsel.value, session_key=session_key, now_unix=clock()))

        def do_GET(self):
            if self.path == "/health":
                self._write(200, b'{"ok":true,"authority":false}', "application/json; charset=utf-8"); return
            if self.path == "/login":
                self._write(200, _login_html(), "text/html; charset=utf-8"); return
            if self.path == "/" or self.path.startswith("/?"):
                if not self._session_ok():
                    self._write(303, location="/login"); return
                self._write(200, MOBILE_HTML_V2.encode("utf-8"), "text/html; charset=utf-8"); return
            if self.path == "/api/observer":
                if not self._session_ok():
                    self._write(401); return
                try:
                    body = _verified_json(provider(), signing_key=signing_key, now_unix=clock())
                except RemoteGatewayV4Error:
                    self._write(503); return
                self._write(200, body, "application/json; charset=utf-8"); return
            self._write(404)

        def do_POST(self):
            if self.path != "/session":
                self._write(405); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._write(400); return
            if length < 1 or length > 4096:
                self._write(413); return
            body = self.rfile.read(length).decode("utf-8", "strict")
            password = parse_qs(body, keep_blank_values=True).get("password", [""])[0]
            candidate = sha256(password.encode("utf-8")).digest()
            if not hmac.compare_digest(candidate, login_hash):
                self._write(401, _login_html(True), "text/html; charset=utf-8"); return
            token = issue_session_v4(session_key=session_key, now_unix=clock(), ttl_seconds=session_ttl_seconds)
            cookie = f"{_COOKIE}={token}; Path=/; Max-Age={session_ttl_seconds}; HttpOnly; Secure; SameSite=Strict"
            self._write(303, cookie=cookie, location="/")

        def do_PUT(self): self._write(405)
        def do_PATCH(self): self._write(405)
        def do_DELETE(self): self._write(405)
        def log_message(self, format, *args): return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
