#!/usr/bin/env python3
"""Koschei Lang Pi Mainnet entry gateway.

This tiny stdlib-only reverse proxy gives the linked Pi Mainnet project a
separate production origin while the canonical app/backend stays in the
existing Web3 Hub service. Mainnet payments are fail-closed until explicitly
enabled after the Mainnet wallet and API key are configured.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.getenv(
    "PI_MAINNET_UPSTREAM",
    "https://koschei-web3-hub-production.up.railway.app",
).rstrip("/")
PAYMENTS_ENABLED = os.getenv("PI_MAINNET_PAYMENTS_ENABLED", "false").lower() == "true"
VALIDATION_KEY = os.getenv("PI_MAINNET_VALIDATION_KEY", "").strip()
PORT = int(os.getenv("PORT", "8080"))

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
PAYMENT_PATH_PREFIXES = (
    "/api/pi/payment/",
    "/api/pi/download-ticket",
    "/api/pi/download-file",
)


def _mainnet_html(body: bytes) -> bytes:
    """Make Pi SDK initialization Mainnet-safe without changing canonical source."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    for old, new in (
        ("sandbox: true", "sandbox: false"),
        ("sandbox:true", "sandbox:false"),
        ('"sandbox": true', '"sandbox": false'),
        ('"sandbox":true', '"sandbox":false'),
    ):
        text = text.replace(old, new)
    return text.encode("utf-8")


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("pi-mainnet-gateway: " + (fmt % args) + "\n")

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def _handle(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        if parsed.path == "/validation-key.txt" and VALIDATION_KEY:
            body = (VALIDATION_KEY + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        if not PAYMENTS_ENABLED and parsed.path.startswith(PAYMENT_PATH_PREFIXES):
            body = b"Pi Mainnet payments are not enabled yet\n"
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        target = UPSTREAM + self.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        data = self.rfile.read(length) if length else None
        headers = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP or lower in {"host", "content-length"}:
                continue
            headers[key] = value
        upstream_host = urllib.parse.urlsplit(UPSTREAM).netloc
        headers["Host"] = upstream_host
        headers["X-Forwarded-Host"] = self.headers.get("Host", "")
        headers["X-Koschei-Pi-Network"] = "mainnet"

        request = urllib.request.Request(
            target,
            data=data,
            headers=headers,
            method=self.command,
        )
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            response = exc
        except Exception as exc:
            body = ("upstream unavailable: " + str(exc) + "\n").encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        with response:
            raw = b"" if self.command == "HEAD" else response.read()
            content_type = response.headers.get("Content-Type", "")
            if raw and "text/html" in content_type.lower():
                raw = _mainnet_html(raw)

            self.send_response(response.status)
            for key, value in response.headers.items():
                lower = key.lower()
                if lower in HOP_BY_HOP or lower in {"content-length", "content-encoding"}:
                    continue
                if lower == "location" and value.startswith(UPSTREAM):
                    value = value[len(UPSTREAM):] or "/"
                self.send_header(key, value)
            self.send_header("X-Koschei-Pi-Network", "mainnet")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if self.command != "HEAD" and raw:
                self.wfile.write(raw)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Gateway)
    print(f"Koschei Lang Pi Mainnet gateway listening on :{PORT} -> {UPSTREAM}")
    server.serve_forever()
