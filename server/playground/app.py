"""Koschei playground: compile and run untrusted Koschei programs safely.

Every submitted program goes through three layers before it can run:

1. Language policy. ``ks caps --deny ...`` rejects, at compile time, any
   program whose capability manifest requests disk, network, environment,
   process, serve, persistence or input authority. Only pure computation
   (plus clock and random) reaches ``ks run``. This is the language's own
   guarantee, shown live.
2. Process sandbox. Each step runs in a fresh temporary directory with an
   empty environment, CPU/memory/file-size/open-file limits and a wall-clock
   timeout, and the interpreter step budget is capped.
3. Service limits. Request body size and per-client request rate are bounded.

Only the Python standard library is used.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from koschei import untrusted
from koschei.untrusted import MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES, SIDE_EFFECT_DOMAINS, outcome
from koschei.untrusted import truncate as _truncate

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"
# The public product site (commercial/lang-site) is served from the same
# process so one service hosts both the landing page and /play.
SITE_DIR = Path(os.environ.get("KOSCHEI_SITE_DIR", HERE.parent.parent / "commercial" / "lang-site"))
SITE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/agents": ("agents.html", "text/html; charset=utf-8"),
    "/security-guide.html": ("security-guide.html", "text/html; charset=utf-8"),
    "/security-guide.tr.html": ("security-guide.tr.html", "text/html; charset=utf-8"),
    "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
    "/sitemap.xml": ("sitemap.xml", "application/xml; charset=utf-8"),
    "/llms.txt": ("llms.txt", "text/plain; charset=utf-8"),
    "/.well-known/security.txt": ("security.txt", "text/plain; charset=utf-8"),
    "/security.txt": ("security.txt", "text/plain; charset=utf-8"),
}
# Paths people and crawlers look for that live as sections of the home page.
SITE_REDIRECTS = {
    "/pricing": "/#pricing",
    "/faq": "/#faq",
    "/about": "/#features",
}
SITE_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
)
PLAY_CSP = SITE_CSP.replace("connect-src 'none'", "connect-src 'self'")
# When set, page requests arriving on a platform hostname (*.up.railway.app)
# are redirected to this canonical host so one address is shared and indexed.
CANONICAL_HOST = os.environ.get("KOSCHEI_CANONICAL_HOST", "")

RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60

# Capability domains a playground program may never request.
DENIED_DOMAINS = SIDE_EFFECT_DOMAINS


def evaluate(source: str, action: str, lang: str = "en") -> dict:
    """Check, and for action == "run" also execute, one Koschei program."""
    return untrusted.evaluate(source, action, lang, DENIED_DOMAINS)


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            recent = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self.hits[key] = recent
                return False
            recent.append(now)
            self.hits[key] = recent
            if len(self.hits) > 10_000:
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
            return True


LIMITER = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


class Handler(BaseHTTPRequestHandler):
    server_version = "KoscheiPlayground/1"

    def _send(self, status: int, body: bytes, content_type: str, csp: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _client(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        return forwarded.split(",")[0].strip() or self.client_address[0]

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        host = self.headers.get("Host", "").split(":")[0].lower()
        if CANONICAL_HOST and host.endswith(".up.railway.app") and path != "/health":
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", f"https://{CANONICAL_HOST}{self.path}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in SITE_REDIRECTS:
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", SITE_REDIRECTS[path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        site = SITE_FILES.get(path)
        if path in ("/play", "/play/"):
            self._send(HTTPStatus.OK, INDEX_HTML.read_bytes(), "text/html; charset=utf-8", PLAY_CSP)
        elif site and (SITE_DIR / site[0]).is_file():
            self._send(HTTPStatus.OK, (SITE_DIR / site[0]).read_bytes(), site[1], SITE_CSP)
        elif path in ("/", "/index.html"):
            # No product site bundled: the playground is the home page.
            self._send(HTTPStatus.OK, INDEX_HTML.read_bytes(), "text/html; charset=utf-8", PLAY_CSP)
        elif path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
        elif path == "/health":
            self._json(HTTPStatus.OK, {"ok": True})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/evaluate":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not LIMITER.allow(self._client()):
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited", "message": "Too many requests; wait a minute and try again."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_SOURCE_BYTES + 1024:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too_large", "message": f"Programs are limited to {MAX_SOURCE_BYTES // 1024} KB."})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            source = payload["source"]
            action = payload.get("action", "run")
            lang = payload.get("lang", "en")
            if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
                raise ValueError("source")
            result = evaluate(source, action, lang)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "message": "Send JSON with a 'source' string and action 'check' or 'run'."})
            return
        log_event(result)
        self._json(HTTPStatus.OK, result)

    def log_message(self, fmt: str, *args) -> None:  # keep logs free of program source
        sys.stdout.write("%s %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()


def log_event(result: dict) -> None:
    """Aggregate usage line: no source code, no client address."""
    domains = sorted(untrusted.requested_domains(result.get("manifest")))
    event = {"event": "evaluate", "action": result["action"], "outcome": outcome(result), "domains": domains}
    sys.stdout.write("PLAYGROUND " + json.dumps(event, sort_keys=True) + "\n")
    sys.stdout.flush()


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
