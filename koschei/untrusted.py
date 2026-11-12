"""Check and run Koschei source that the caller does not trust.

Used by the web playground and the MCP server. A program goes through two
layers before it can run:

1. Language policy. ``ks caps --json --deny ...`` type-checks the program and
   reads its capability manifest. If the program requests a denied domain,
   even narrowed, it is rejected and none of its code executes.
2. Process limits. Every step runs in a child process in a fresh temporary
   directory with a minimal environment, CPU/memory/file-size/open-file
   limits, a wall-clock timeout and a capped interpreter step budget.

Only the Python standard library is used. The limits rely on ``resource``,
so this module works on Unix-like systems only.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_SOURCE_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
WALL_TIMEOUT_SECONDS = 10
CPU_SECONDS = 5
MEMORY_BYTES = 512 * 1024 * 1024
MAX_STEPS = 200_000

# Every capability domain, in manifest order.
ALL_DOMAINS = ("disk", "net", "env", "process", "serve", "persist", "input", "clock", "random", "db")
# Domains that reach outside the process. Clock and random are left out.
SIDE_EFFECT_DOMAINS = ("disk", "net", "env", "process", "serve", "persist", "input", "db")

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


def truncate(text: str) -> str:
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
    # A path inside our temp dir means nothing to the caller.
    clean = lambda s: truncate(s.replace(workdir + os.sep, "").replace(workdir, "."))
    return {"exit_code": done.returncode, "stdout": clean(done.stdout), "stderr": clean(done.stderr), "timed_out": False}


def evaluate(source: str, action: str, lang: str = "en", denied: tuple[str, ...] = SIDE_EFFECT_DOMAINS) -> dict:
    """Check, and for action == "run" also execute, one Koschei program.

    ``denied`` lists the capability domains the program may not request.
    The result's ``stage`` is ``policy`` (rejected by the deny list),
    ``check`` (did not compile, or only checked) or ``run``.
    """
    if action not in ("check", "run"):
        raise ValueError("action must be 'check' or 'run'")
    unknown = set(denied) - set(ALL_DOMAINS)
    if unknown:
        raise ValueError(f"unknown capability domain: {', '.join(sorted(unknown))}")
    if lang not in ("en", "tr"):
        lang = "en"
    with tempfile.TemporaryDirectory(prefix="ks-untrusted-") as workdir:
        Path(workdir, "main.ks").write_text(source, encoding="utf-8")
        deny: list[str] = []
        for domain in denied:
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


def requested_domains(manifest: dict | None) -> list[str]:
    """The capability domains a manifest asks for, in manifest order."""
    manifest = manifest or {}
    found = {g.get("domain", "") for g in manifest.get("grants", [])} | set(manifest.get("required_domains", []))
    return [d for d in ALL_DOMAINS if d in found]
