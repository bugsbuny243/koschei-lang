"""Serve the minimal Koschei Pi production bridge.

This server is intentionally dependency-free. It exposes the production landing
page and Pi's required /validation-key.txt route. The validation value is read
from PI_DOMAIN_VALIDATION_KEY and is never hard-coded into source.
"""
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "distribution" / "pi-production-web" / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "KoscheiPiBridge/1"

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self._write(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/validation-key.txt":
            value = os.environ.get("PI_DOMAIN_VALIDATION_KEY", "").strip()
            if not value:
                self._write(503, b"validation key unavailable\n", "text/plain; charset=utf-8")
                return
            self._write(200, (value + "\n").encode("utf-8"), "text/plain; charset=utf-8")
            return
        if path in {"/", "/index.html"}:
            if not INDEX.is_file():
                self._write(500, b"production page unavailable\n", "text/plain; charset=utf-8")
                return
            self._write(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        self._write(404, b"not found\n", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        print("KOSCHEI PI HTTP:", format % args)

    def _write(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    if not (1 <= port <= 65535):
        raise ValueError("PORT must be between 1 and 65535")
    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"KOSCHEI PI PRODUCTION: http://{host}:{port}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
