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
import resource
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"
# The public product site (commercial/lang-site) is served from the same
# process so one service hosts both the landing page and /play.
SITE_DIR = Path(os.environ.get("KOSCHEI_SITE_DIR", HERE.parent.parent / "commercial" / "lang-site"))
SITE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/security-guide.html": ("security-guide.html", "text/html; charset=utf-8"),
    "/security-guide.tr.html": ("security-guide.tr.html", "text/html; charset=utf-8"),
    "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
    "/sitemap.xml": ("sitemap.xml", "application/xml; charset=utf-8"),
}
SITE_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
)
PLAY_CSP = SITE_CSP.replace("connect-src 'none'", "connect-src 'self'")

MAX_SOURCE_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
WALL_TIMEOUT_SECONDS = 10
CPU_SECONDS = 5
MEMORY_BYTES = 512 * 1024 * 1024
MAX_STEPS = 200_000
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60

# Capability domains a playground program may never request.
DENIED_DOMAINS = ("disk", "net", "env", "process", "serve", "persist", "input")

KS = [sys.executable, "-m", "koschei"]


def _limit_child() -> None:
    """Applied in the child just before exec."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setsid()


def _child_env() -> dict[str, str]:
    # No inherited secrets; only what Python needs to start.
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}


def _truncate(text: str) -> str:
    data = text.encode("utf-8", "replace")
    if len(data) <= MAX_OUTPUT_BYTES:
        return text
    return data[:MAX_OUTPUT_BYTES].decode("utf-8", "ignore") + "\n… output truncated"


def _ks(args: list[str], workdir: str) -> dict:
    try:
        done = subprocess.run(
            KS + args,
            cwd=workdir,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=WALL_TIMEOUT_SECONDS,
            preexec_fn=_limit_child,
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": f"Stopped: the program exceeded the {WALL_TIMEOUT_SECONDS}s time limit.", "timed_out": True}
    # A path inside our temp dir means nothing to the visitor.
    clean = lambda s: _truncate(s.replace(workdir + os.sep, "").replace(workdir, "."))
    return {"exit_code": done.returncode, "stdout": clean(done.stdout), "stderr": clean(done.stderr), "timed_out": False}


def evaluate(source: str, action: str, lang: str = "en") -> dict:
    """Check, and for action == "run" also execute, one Koschei program."""
    if action not in ("check", "run"):
        raise ValueError("action must be 'check' or 'run'")
    if lang not in ("en", "tr"):
        lang = "en"
    with tempfile.TemporaryDirectory(prefix="ks-playground-") as workdir:
        Path(workdir, "main.ks").write_text(source, encoding="utf-8")
        deny: list[str] = []
        for domain in DENIED_DOMAINS:
            deny += ["--deny", domain]
        # `ks caps` type-checks the program and enforces the deny policy.
        policy = _ks(["--lang", lang, "caps", "--json", "main.ks", *deny], workdir)
        result = {"action": action, "stage": "check", "policy": policy, "manifest": None, "ran": False}
        if policy["exit_code"] in (0, 2):
            try:
                result["manifest"] = json.loads(policy["stdout"])
                policy["stdout"] = ""
            except ValueError:
                pass
        if policy["exit_code"] != 0:
            result["stage"] = "policy" if policy["exit_code"] == 2 else "check"
            return result
        if action == "check":
            return result
        result["stage"] = "run"
        result["run"] = _ks(["--lang", lang, "run", "--max-steps", str(MAX_STEPS), "main.ks"], workdir)
        result["ran"] = True
        return result


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


def outcome(result: dict) -> str:
    """One word describing how an evaluation ended."""
    if result["stage"] == "policy":
        return "blocked"
    if not result["ran"]:
        return "checked" if result["policy"]["exit_code"] == 0 else "compile_error"
    run = result["run"]
    if run["timed_out"]:
        return "timeout"
    return "ok" if run["exit_code"] == 0 else "runtime_error"


def log_event(result: dict) -> None:
    """Aggregate usage line: no source code, no client address."""
    manifest = result.get("manifest") or {}
    domains = sorted({g.get("domain", "") for g in manifest.get("grants", [])} | set(manifest.get("required_domains", [])))
    event = {"event": "evaluate", "action": result["action"], "outcome": outcome(result), "domains": domains}
    sys.stdout.write("PLAYGROUND " + json.dumps(event, sort_keys=True) + "\n")
    sys.stdout.flush()


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
