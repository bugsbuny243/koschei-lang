"""MCP server that lets an AI agent run Koschei code under a capability policy.

The agent writes a Koschei program instead of a shell command or a Python
script. Before anything runs, the compiler reports exactly which disk paths,
network origins, environment variables and other authority the program asks
for. The person who started this server decides which capability domains are
allowed at all; a program that asks for anything else is rejected and none of
its code executes.

    ks-mcp                                   # pure computation only (the default)
    ks-mcp --allow-read /srv/reports --allow-net https://api.example.com

The agent cannot widen the policy: it is fixed by the command line of the
process the user started. Transport is MCP over stdio (newline-delimited
JSON-RPC 2.0). Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from typing import Any

from . import untrusted

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "koschei", "title": "Koschei", "version": "0.14.0"}

DOMAIN_LABELS = {
    "disk": "Disk",
    "net": "Network",
    "env": "Environment variable",
    "process": "Process",
    "serve": "HTTP server",
    "persist": "Persistent state",
    "db": "Database",
    "input": "Program input",
    "clock": "Clock",
    "random": "Random numbers",
}

_SOURCE = {
    "type": "string",
    "description": "Complete Koschei source with a `main` function. Call koschei_guide first if you have not written Koschei before.",
}

QUICK_REFERENCE = """\
# Koschei quick reference

```ks
fn main() {
    let name = "Ada"            // immutable
    let mut count = 2           // mutable
    count = count + 1
    println("{name} has {count} items")   // any expression inside {}
}
```

- Types: Int, Float, String, Bool, List<T>, Map<String, V>, Option<T>, Result<T, E>. No null.
- `if / else if / else`, `while`, `for item in list`, `break`, `continue`. No range loop: count with `while`.
- Functions: `fn area(w: Int, h: Int) -> Int { return w * h }`. Names start lowercase; types start uppercase.
- Errors are values: `fn f() -> Int or Error`, `return Error("why")`.
  Handle with `or default`, `or return Error("...")`, or `or { ... }`.
- Lists are immutable values: `xs.push(x)` returns a new list. Methods: length, get, push, contains, sort, filter, map.
  `get`, `sort`, `filter`, `map` can fail: `xs.get(0) or 0`. `filter`/`map` take a function name or a lambda `fn(x: Int) -> Bool { return x > 0 }`; a lambda cannot use outer variables.
- Empty collections need a type: `let mut xs: List<Int> = []`, `let mut m: Map<String, Int> = {}`.
- Maps: `{"a": 1}`, `m.get("a") or 0`, `m.set("b", 2)` (returns a new map), `m.keys()`, `m.contains("a")`.
- Strings: length, contains, trim, split(sep) or [], sep.join(list), to_int() or 0, to_float() or 0.0.
- Structs: `struct Point { x: Int, y: Int }`, `Point { x: 1, y: 2 }`, `p.x`.
- Enums: `enum Shape { Circle(Int), Empty }`; build with `Circle(2)`, `Empty()`;
  `match s { Circle(r) => r, Empty => 0 }` must cover every variant.
- `print` writes without a newline; `println` adds one.
- Math: `import math`, then `math.min`, `math.max`, `math.sign` (Int), `math.abs(x) or 0`, `math.pow(b, e) or 0`,
  `math.clamp(x, lo, hi) or 0`, `math.gcd(a, b) or 0`, `math.min_float`, `math.max_float`, `math.abs_float`.
- Dates: `import time`, then `time.iso_utc(ms) or "?"` (UTC, ms since 1970), `let t = time.utc(ms) or return Error("x")`
  gives `t.year`, `t.month`, `t.day`, `t.hour`, `t.minute`, `t.second`, `t.weekday`; `time.from_utc(y, mo, d, h, mi, s) or 0`.
- Operators: `+ - * / %`, `== != < <= > >=`, `&& || !`. `Int / Int` is integer division. `or` is only for errors.
- `join` joins Strings only. Turn a number into a String with interpolation: `"{n}"`.
- `match` is an expression (`let label = match s { ... }`) or a statement. Arms are separated by commas.
- `let x = f() or { println("failed") }` runs the block when `f` fails. Statements end at the newline; no semicolons.
- `fn main()` may `return Error("why")`, also through `or return Error(...)`: the program stops with that message.
- Inside a string literal write `\\"` for a double quote.
- JSON: `let data = parse_json(text) or return Error("not JSON")`, then read with
  `json_get(data, "key")`, `json_at(data, 0)`, `json_text(d)`, `json_int(d)`, `json_float(d)`, `json_bool(d)`,
  `json_length(d)`, `json_keys(d)`, `json_items(d)` (all `or`-handled), `json_has(data, "key")`, `json_kind(d)`.
  Write `{` and `}` inside a string literal as `\\{` and `\\}`. `encode_json(data)` gives the text back.
  Bind each step with `let`: `let f = json_get(data, "n") or return Error("no n")` then `json_int(f) or 0`.
- Writing JSON: `import json`, then `json.object({"name": json.string(n), "n": json.int(3), "xs": json.array([json.int(1)])})`;
  also `json.bool(b)`, `json.null()`, `json.float(f) or "null"`. The result is a String.
- URLs and forms: `import http`, then `http.route("/users/:id", target)` (Option of a Map; `or return ...`),
  `http.query(target) or return Error("bad query")`, `http.params(body)`, `http.decode(s)`, `http.path_of(target)`,
  `http.escape_html(text)` before putting text in a page, `http.cookies(request.header("Cookie") or "")`.
- Database (only when the server allows `db`): `let db = caps.db.allow("/abs/app.db", 1000, 10485760, 2000)`,
  `db.exec("INSERT INTO t (a) VALUES (?)", json.array([json.string(a)])) or return Error("x")` (rows changed),
  `db.query("SELECT a FROM t WHERE id = ?", json.array([json.int(id)]))` gives Data (array of row objects).
  SQL must be a literal string; values go only through `?` and the JSON array.

## Capabilities

A program has no access to anything outside itself unless `main` takes
`caps: SystemCaps` and narrows a token from it:

```ks
fn main(caps: SystemCaps) {
    let data = caps.disk.allow_read_only("/data")      // or allow(prefix) for write access
    let text = data.read("/data/input.txt") or "missing"
    let api = caps.net.allow("https://api.example.com")
    let body = api.get("https://api.example.com/v1/items") or "failed"
    let home = caps.env.allow("HOME").get("HOME") or ""
    println(text)
}
```

| Root | Narrow with | Then |
|---|---|---|
| caps.disk | allow(prefix), allow_read_only(prefix) | read(path), list(path), write(path, text), delete(path) |
| caps.net | allow(origin) | get(url), post(url, content_type, body) |
| caps.env | allow(name) | get(name) |
| caps.input | allow(max_stdin_bytes) | args(), read_text() |
| caps.clock | allow(resolution_ms) | now_ms(), monotonic_ms() |
| caps.random | allow(max_bytes) | hex(count), below(bound) |

Pass a narrowed token to a function as a typed parameter (`disk: DiskReadCaps`,
`net: NetCaps`). Use literal strings for prefixes and origins so the manifest
is exact. Ask only for what the task needs: every grant is shown to the user.
"""


def describe_manifest(manifest: dict | None) -> list[str]:
    """Human-readable lines for what a program asks for."""
    if not manifest:
        return []
    if not manifest.get("has_capabilities"):
        return ["Requests no capabilities: pure computation, no disk, network, environment or process access."]
    lines = []
    operations = manifest.get("operations") or {}
    for grant in manifest.get("grants", []):
        domain = grant.get("domain", "")
        scope = "a value computed at run time" if grant.get("dynamic") else grant.get("scope", "")
        access = ""
        if domain == "disk":
            access = " (read-only)" if grant.get("read_only") else " (read and write)"
        used = operations.get(domain) or []
        suffix = f"; uses {', '.join(used)}" if used else ""
        lines.append(f"{DOMAIN_LABELS.get(domain, domain)}: {scope}{access}, line {grant.get('line')}{suffix}")
    for domain in manifest.get("required_domains", []):
        lines.append(f"{DOMAIN_LABELS.get(domain, domain)}: must be supplied by the caller")
    if not manifest.get("exact", True):
        lines.append("The manifest is not exact: at least one scope is computed at run time.")
    return lines


def _norm_path(path: str) -> str:
    return posixpath.normpath("/" + path.strip().lstrip("/"))


def _under(path: str, roots: tuple[str, ...]) -> bool:
    path = _norm_path(path)
    return any(root == "/" or path == root or path.startswith(root + "/") for root in roots)


def _norm_origin(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


class Policy:
    """What the person who started the server lets programs ask for.

    A domain is either allowed as a whole (``domains``) or only for listed
    scopes: disk paths to read or write, network origins, environment names.
    Everything else is denied. Clock and random never leave the process and
    are always allowed.
    """

    def __init__(self, domains=(), read=(), write=(), net=(), env=()) -> None:
        unknown = set(domains) - set(untrusted.SIDE_EFFECT_DOMAINS)
        if unknown:
            raise ValueError(f"unknown capability domain: {', '.join(sorted(unknown))}")
        self.domains = set(domains) | {"clock", "random"}
        self.write = tuple(_norm_path(p) for p in write)
        self.read = tuple(_norm_path(p) for p in read) + self.write
        self.net = tuple(_norm_origin(o) for o in net)
        self.env = tuple(env)
        scoped = {"disk": self.read, "net": self.net, "env": self.env}
        self.scoped = {d for d, entries in scoped.items() if entries and d not in self.domains}
        self.allowed = tuple(d for d in untrusted.ALL_DOMAINS if d in self.domains or d in self.scoped)
        self.denied = tuple(d for d in untrusted.ALL_DOMAINS if d not in self.allowed)

    def describe(self) -> str:
        parts = []
        for domain in self.allowed:
            if domain not in self.scoped:
                parts.append(domain)
            elif domain == "disk":
                readable = [p for p in self.read if p not in self.write]
                if readable:
                    parts.append("disk read under " + ", ".join(readable))
                if self.write:
                    parts.append("disk read and write under " + ", ".join(self.write))
            elif domain == "net":
                parts.append("network to " + ", ".join(self.net))
            else:
                parts.append("environment variables " + ", ".join(self.env))
        return "; ".join(parts)

    def violations(self, manifest: dict | None) -> list[str]:
        """Grants in scoped domains that fall outside the allowed scopes."""
        found: list[str] = []
        manifest = manifest or {}
        for grant in manifest.get("grants", []):
            domain, scope = grant.get("domain"), str(grant.get("scope", ""))
            if domain not in self.scoped:
                continue
            where = f"line {grant.get('line')}"
            if grant.get("dynamic"):
                found.append(f"{DOMAIN_LABELS[domain]} scope is computed at run time ({where}); use a literal so it can be checked")
            elif domain == "disk":
                if grant.get("read_only"):
                    if not _under(scope, self.read):
                        found.append(f"Disk read of {scope} ({where}) is outside the allowed paths")
                elif not _under(scope, self.write):
                    found.append(f"Disk write access to {scope} ({where}) is outside the allowed writable paths")
            elif domain == "net":
                if _norm_origin(scope) not in self.net:
                    found.append(f"Network access to {scope} ({where}) is not an allowed origin")
            elif scope not in self.env:
                found.append(f"Environment variable {scope} ({where}) is not allowed")
        for domain in manifest.get("required_domains", []):
            if domain in self.scoped:
                found.append(f"{DOMAIN_LABELS[domain]} authority without a literal scope cannot be checked")
        return found


class Server:
    def __init__(self, policy: Policy | None = None) -> None:
        self.policy = policy or Policy()

    # -- tools ---------------------------------------------------------

    def tools(self) -> list[dict]:
        schema = {"type": "object", "properties": {"source": _SOURCE}, "required": ["source"], "additionalProperties": False}
        return [
            {
                "name": "koschei_guide",
                "title": "Koschei language guide",
                "description": "Returns a reference for writing Koschei, a capability-secure language. Read it before writing a program.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "koschei_check",
                "title": "Check a Koschei program",
                "description": "Compiles a Koschei program without running it and reports its capability manifest: "
                "every disk path, network origin and other authority it asks for, and whether this server's policy "
                "would allow it. Nothing executes.",
                "inputSchema": schema,
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "koschei_run",
                "title": "Run a Koschei program",
                "description": "Compiles and runs a Koschei program under this server's policy. "
                f"Allowed: {self.policy.describe()}. A program that asks for anything else is rejected "
                "before a single line executes. The result includes the capability manifest and the output.",
                "inputSchema": schema,
                "annotations": {"readOnlyHint": False, "openWorldHint": bool(set(self.policy.allowed) & {"net", "disk", "process"})},
            },
        ]

    def call(self, name: str, arguments: dict) -> dict:
        if name == "koschei_guide":
            return self._text(QUICK_REFERENCE)
        if name not in ("koschei_check", "koschei_run"):
            raise LookupError(name)
        source = arguments.get("source")
        if not isinstance(source, str) or not source.strip():
            return self._text("`source` must be a non-empty string of Koschei code.", error=True)
        if len(source.encode("utf-8")) > untrusted.MAX_SOURCE_BYTES:
            return self._text(f"The program is larger than {untrusted.MAX_SOURCE_BYTES // 1024} KB.", error=True)
        # Always check first: the scope policy is decided on the manifest, before any code runs.
        result = untrusted.evaluate(source, "check", "en", self.policy.denied)
        violations: list[str] = []
        if untrusted.outcome(result) == "checked":
            violations = self.policy.violations(result.get("manifest"))
            if not violations and name == "koschei_run":
                result = untrusted.evaluate(source, "run", "en", self.policy.denied)
        return self._report(result, violations)

    def _report(self, result: dict, violations: list[str]) -> dict:
        outcome = "blocked" if violations else untrusted.outcome(result)
        manifest = result.get("manifest")
        policy = result["policy"]
        lines: list[str] = []
        if outcome == "blocked":
            reasons = violations or [
                f"{DOMAIN_LABELS[d]} access is not allowed" for d in untrusted.requested_domains(manifest) if d in self.policy.denied
            ]
            lines.append("BLOCKED before running. The program asks for authority this server does not allow:")
            lines.extend("- " + reason for reason in reasons)
            lines.append("Nothing was executed. Allowed: " + self.policy.describe() + ".")
            lines.append("To proceed, the user must restart the server with a wider policy, or the program must ask for less.")
        elif outcome == "compile_error":
            lines.append("The program does not compile. Nothing was executed.")
            lines.append((policy["stderr"] or policy["stdout"]).strip())
        elif outcome == "checked":
            lines.append("The program compiles and stays within the policy. It was not run.")
        elif outcome == "ok":
            lines.append("Ran successfully.")
        elif outcome == "timeout":
            lines.append("Stopped: the program exceeded the time limit.")
        else:
            lines.append("The program ran and stopped with an error.")
        described = describe_manifest(manifest)
        if described:
            lines.append("")
            lines.append("Capability manifest:")
            lines.extend("- " + line for line in described)
        if result["ran"]:
            run = result["run"]
            if run["stdout"]:
                lines += ["", "Output:", run["stdout"].rstrip("\n")]
            if run["stderr"]:
                lines += ["", "Errors:", run["stderr"].rstrip("\n")]
        structured = {
            "outcome": outcome,
            "executed": result["ran"],
            "policy": self.policy.describe(),
            "requested_domains": untrusted.requested_domains(manifest),
            "manifest": manifest,
        }
        if violations:
            structured["violations"] = violations
        if result["ran"]:
            structured["stdout"] = result["run"]["stdout"]
            structured["stderr"] = result["run"]["stderr"]
            structured["exit_code"] = result["run"]["exit_code"]
        is_error = outcome in ("blocked", "compile_error", "timeout", "runtime_error")
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "structuredContent": structured, "isError": is_error}

    @staticmethod
    def _text(text: str, error: bool = False) -> dict:
        return {"content": [{"type": "text", "text": text}], "isError": error}

    # -- JSON-RPC ------------------------------------------------------

    def handle(self, message: Any) -> dict | None:
        """Return the response for one JSON-RPC message, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid request")
        method, request_id = message["method"], message.get("id")
        if "id" not in message:
            return None  # notifications (e.g. notifications/initialized) need no reply
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(request_id, -32602, "params must be an object")
        if method == "initialize":
            return _result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
                "instructions": "Write Koschei programs for tasks that need computation or controlled access to files and "
                "the network. Call koschei_guide first. Every program's capability manifest is reported before it runs; "
                "this server allows: " + self.policy.describe() + ".",
            })
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": self.tools()})
        if method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _error(request_id, -32602, "tools/call needs a tool name and an arguments object")
            try:
                return _result(request_id, self.call(name, arguments))
            except LookupError:
                return _error(request_id, -32602, f"Unknown tool: {name}")
        return _error(request_id, -32601, f"Method not found: {method}")

    def serve(self, stdin=None, stdout=None) -> None:
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                response = _error(None, -32700, "Parse error")
            else:
                response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()


def _result(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ks-mcp",
        description="MCP server (stdio) that runs Koschei programs under a capability policy. "
        "With no options, programs may only compute (plus clock and random).",
    )
    parser.add_argument("--allow-read", action="append", default=[], metavar="PATH", help="directory programs may read; repeatable")
    parser.add_argument("--allow-write", action="append", default=[], metavar="PATH", help="directory programs may read and write; repeatable")
    parser.add_argument("--allow-net", action="append", default=[], metavar="ORIGIN", help="origin programs may reach, e.g. https://api.example.com; repeatable")
    parser.add_argument("--allow-env", action="append", default=[], metavar="NAME", help="environment variable programs may read; repeatable")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        choices=untrusted.SIDE_EFFECT_DOMAINS,
        metavar="DOMAIN",
        help="allow a whole capability domain with no scope limit; repeatable. One of: " + ", ".join(untrusted.SIDE_EFFECT_DOMAINS),
    )
    args = parser.parse_args(argv)
    Server(Policy(args.allow, args.allow_read, args.allow_write, args.allow_net, args.allow_env)).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
