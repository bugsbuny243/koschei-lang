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
import re
import subprocess
from decimal import Decimal
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
# Static package registry (docs/PACKAGES_V1.md, phase 2): plain files, no code.
REGISTRY_DIR = Path(os.environ.get("KOSCHEI_REGISTRY_DIR", HERE.parent.parent / "registry"))
REGISTRY_PATH = re.compile(
    r"^/registry/(index/[a-z][a-z0-9_-]*\.json|archives/([a-z][a-z0-9_-]*)/\2-\d+\.\d+\.\d+\.tar)$"
)
SITE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/tools": ("business-tools.html", "text/html; charset=utf-8"),
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
BUSINESS_CSP = SITE_CSP.replace("connect-src 'none'", "connect-src 'self'")
BUSINESS_ENGINE = Path(os.environ.get(
    "KOSCHEI_BUSINESS_ENGINE", HERE.parent.parent / "products" / "business_web" / "engine.ks"
))
BUSINESS_MAX_BYTES = 8192
BUSINESS_SLOTS = threading.BoundedSemaphore(2)

# When set, page requests arriving on a platform hostname (*.up.railway.app)
# are redirected to this canonical host so one address is shared and indexed.
CANONICAL_HOST = os.environ.get("KOSCHEI_CANONICAL_HOST", "")


def playground_mode() -> str:
    mode = os.environ.get("KOSCHEI_PLAYGROUND_MODE", "enabled")
    if mode not in ("enabled", "disabled"):
        raise ValueError("KOSCHEI_PLAYGROUND_MODE must be enabled or disabled")
    return mode


PLAYGROUND_MODE = playground_mode()
UNAVAILABLE_HTML = b"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Playground temporarily unavailable - Koschei</title>
<style>body{margin:0;background:#0d1215;color:#dde6e2;font:16px/1.6 system-ui,sans-serif}
main{max-width:640px;margin:12vh auto;padding:24px}h1{font-size:28px}
p{color:#a7b4ae}a{color:#9fd9bd}</style>
<main><h1>Playground temporarily unavailable</h1>
<p>Online code execution is paused. You can still browse the Koschei website.</p>
<p><a href="/">Back to Koschei</a></p></main></html>"""

RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_CONCURRENT_EVALUATIONS = int(os.environ.get("KOSCHEI_MAX_CONCURRENT_EVALUATIONS", "4"))
EVALUATION_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_EVALUATIONS)

# Capability domains a playground program may never request.
DENIED_DOMAINS = SIDE_EFFECT_DOMAINS


def evaluate(source: str, action: str, lang: str = "en") -> dict:
    """Check, and for action == "run" also execute, one Koschei program."""
    if PLAYGROUND_MODE != "enabled":
        raise untrusted.SandboxUnavailable("Online code execution is disabled")
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
BUSINESS_LIMITER = RateLimiter(15, 60.0)


# The website passes numeric data to a single, committed Koschei source file.
# The caller never supplies source code, paths, capabilities, executable names,
# or CLI arguments. Neither the runtime nor this bridge stores input.
_MONEY = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?\Z", re.ASCII)


def _whole(value: object, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid bounded integer")
    return value


def _cents(value: object, maximum: int = 100_000_000) -> int:
    if not isinstance(value, str) or not _MONEY.fullmatch(value):
        raise ValueError("amount must be a positive decimal string with up to 2 digits")
    cents = int(Decimal(value) * 100)
    if cents > maximum:
        raise ValueError("amount too large")
    return cents


def _nonempty_rows(data: object, limit: int) -> list[dict]:
    if not isinstance(data, list) or not 1 <= len(data) <= limit:
        raise ValueError("expected a bounded nonempty list")
    if not all(isinstance(row, dict) for row in data):
        raise ValueError("invalid row")
    return data


def _business_request(payload: object) -> tuple[str, str, int]:
    """Validate UI JSON, discard descriptions and build numeric-only Koschei input."""
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")
    mode = payload.get("kind")
    if mode == "quote":
        discount = _whole(payload.get("discount"), 100)
        vat = _whole(payload.get("vat"), 100)
        rows = _nonempty_rows(payload.get("items"), 24)
        lines = [f"QUOTE|{discount}|{vat}"]
        for row in rows:
            qty = _whole(row.get("quantity"), 1000)
            if qty == 0:
                raise ValueError("zero quantity")
            lines.append(f"ROW|{qty}|{_cents(row.get('price'))}")
    elif mode == "stock":
        rows = _nonempty_rows(payload.get("items"), 40)
        lines = ["STOCK"]
        for row in rows:
            qty = _whole(row.get("quantity"), 100_000)
            threshold = _whole(row.get("minimum"), 100_000)
            cost = _cents(row.get("cost"))
            lines.append(f"ROW|{qty}|{threshold}|{cost}")
    elif mode == "cash":
        opening = _cents(payload.get("opening"), 1_000_000_000_000)
        rows = _nonempty_rows(payload.get("items"), 40)
        lines = [f"CASH|{opening}"]
        for row in rows:
            kind = row.get("type")
            if kind not in ("income", "expense"):
                raise ValueError("invalid cash transaction")
            amount = _cents(row.get("amount"), 100_000_000_000)
            if amount == 0:
                raise ValueError("zero transaction")
            lines.append(f"{'IN' if kind == 'income' else 'OUT'}|{amount}")
    else:
        raise ValueError("unknown tool")
    source = "\n".join(lines)
    if len(source.encode("ascii")) > BUSINESS_MAX_BYTES:
        raise ValueError("too many items")
    return mode, source, len(rows)


def _integer(raw: str) -> int:
    if not re.fullmatch(r"-?[0-9]{1,16}", raw, re.ASCII):
        raise ValueError("bad engine output")
    return int(raw)


def _business_result(mode: str, output: str, count: int) -> dict:
    """Parse the stable numeric protocol; no reported totals come from Python."""
    rows = [line.strip() for line in output.splitlines() if line.strip()]
    if not rows:
        raise ValueError("empty engine output")
    header = rows[-1].split("|")
    if mode == "quote":
        if len(rows) != 1 or len(header) != 7 or header[:2] != ["OK", "QUOTE"]:
            raise ValueError("quote protocol mismatch")
        subtotal, discount, vat, total, seen = map(_integer, header[2:])
        if seen != count or subtotal < 0 or discount < 0 or vat < 0 or total < 0:
            raise ValueError("quote result invalid")
        return {"kind": mode, "subtotal": subtotal, "discount": discount, "vat": vat, "total": total, "count": seen}
    if mode == "cash":
        if len(rows) != 1 or len(header) != 8 or header[:2] != ["OK", "CASH"]:
            raise ValueError("cash protocol mismatch")
        opening, income, expenses, closing, incoming, outgoing = map(_integer, header[2:])
        if incoming + outgoing != count:
            raise ValueError("cash count mismatch")
        return {"kind": mode, "opening": opening, "income": income, "expenses": expenses,
                "closing": closing, "income_count": incoming, "expense_count": outgoing}
    if mode == "stock":
        if len(header) != 5 or header[:2] != ["OK", "STOCK"] or len(rows) != count + 1:
            raise ValueError("stock protocol mismatch")
        seen, alerts, value = map(_integer, header[2:])
        if seen != count or not 0 <= alerts <= seen:
            raise ValueError("stock count mismatch")
        items = []
        for idx, line in enumerate(rows[:-1], 1):
            parts = line.split("|")
            if len(parts) != 4 or parts[0] != "ROW" or _integer(parts[1]) != idx or parts[2] not in ("LOW", "OK"):
                raise ValueError("stock row mismatch")
            reorder = _integer(parts[3])
            if reorder < 0:
                raise ValueError("negative order")
            items.append({"low": parts[2] == "LOW", "reorder": reorder})
        return {"kind": mode, "count": seen, "alerts": alerts, "inventory_value": value, "items": items}
    raise ValueError("unknown engine mode")


def _business_run(mode: str, source: str, count: int) -> dict:
    if not BUSINESS_ENGINE.is_file():
        raise RuntimeError("business engine missing")
    completed = subprocess.run(
        [sys.executable, "-m", "koschei", "run", str(BUSINESS_ENGINE), "--max-steps", "150000"],
        input=source,
        text=True,
        capture_output=True,
        encoding="utf-8",
        timeout=8,
        cwd=HERE,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) > 8192:
        raise RuntimeError("business engine failed")
    return _business_result(mode, completed.stdout, count)



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
        # Never trust client-supplied forwarding headers for security decisions.
        # A trusted ingress may provide a verified client address via a separate
        # deployment-specific mechanism; the direct peer is the safe default.
        return self.client_address[0]

    def _playground_page(self) -> None:
        if PLAYGROUND_MODE != "enabled":
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, UNAVAILABLE_HTML,
                       "text/html; charset=utf-8", SITE_CSP)
            return
        self._send(HTTPStatus.OK, INDEX_HTML.read_bytes(), "text/html; charset=utf-8", PLAY_CSP)

    def _registry_file(self, path: str) -> None:
        relative = path[len("/registry/"):]
        file = REGISTRY_DIR / relative
        if not file.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        body = file.read_bytes()
        is_index = relative.startswith("index/")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json" if is_index else "application/x-tar")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # Archives never change once published; an index gains versions.
        self.send_header("Cache-Control", "public, max-age=300" if is_index else "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(body)

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
        home = SITE_FILES.get("/")
        if path in ("/play", "/play/") and PLAYGROUND_MODE != "enabled" and home and (SITE_DIR / home[0]).is_file():
            # Execution is paused: send old links and crawlers to the local
            # install section instead of an error page. 302, not 301: the
            # playground comes back when the sandbox does.
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/#start")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path in ("/play", "/play/"):
            self._playground_page()
        elif REGISTRY_PATH.fullmatch(path):
            self._registry_file(path)
        elif site and (SITE_DIR / site[0]).is_file():
            self._send(HTTPStatus.OK, (SITE_DIR / site[0]).read_bytes(), site[1], BUSINESS_CSP if path == "/tools" else SITE_CSP)
        elif path in ("/", "/index.html"):
            # No product site bundled: the playground is the home page.
            self._playground_page()
        elif path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
        elif path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "evaluation_enabled": PLAYGROUND_MODE == "enabled"})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    do_HEAD = do_GET

    def _business_calculate(self) -> None:
        # Strictly separate trusted fixed-function products from /api/evaluate.
        origin = self.headers.get("Origin", "")
        if origin and origin != "https://koschei.dev":
            self._json(HTTPStatus.FORBIDDEN, {"error": "origin_denied"})
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_type"})
            return
        if not BUSINESS_LIMITER.allow(self._client()):
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 1 <= length <= BUSINESS_MAX_BYTES:
            self.close_connection = True
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"})
            return
        try:
            raw = self.rfile.read(length)
            mode, source, count = _business_request(json.loads(raw))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_input", "message": "Check quantities and amounts."})
            return
        if not BUSINESS_SLOTS.acquire(blocking=False):
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "busy"})
            return
        try:
            result = _business_run(mode, source, count)
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
            # Deliberately never send stderr or source to a browser or access log.
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "service_unavailable"})
            return
        finally:
            BUSINESS_SLOTS.release()
        self._json(HTTPStatus.OK, result)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/business/calculate":
            self._business_calculate()
            return
        if self.path != "/api/evaluate":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if PLAYGROUND_MODE != "enabled":
            # Reject before reading the body or invoking any compiler path.
            self.close_connection = True
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "evaluation_disabled",
                "message": "Online code execution is temporarily unavailable.",
            })
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
            if not EVALUATION_SLOTS.acquire(blocking=False):
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "busy", "message": "Playground is busy; retry shortly."})
                return
            try:
                result = evaluate(source, action, lang)
            finally:
                EVALUATION_SLOTS.release()
        except untrusted.SandboxUnavailable:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "sandbox_unavailable", "message": "The evaluation sandbox is unavailable."},
            )
            return
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
    # Fail closed on hosts that disallow required user/mount/network namespaces.
    # Do not expose the playground with a silently weakened sandbox.
    if PLAYGROUND_MODE not in ("enabled", "disabled"):
        raise ValueError("Invalid Playground mode")
    if PLAYGROUND_MODE == "enabled":
        untrusted.require_container_limits()
        untrusted.require_sandbox_ready()
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
