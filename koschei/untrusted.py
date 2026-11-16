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
import shutil
import signal
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


class SandboxUnavailable(RuntimeError):
    """The requested OS sandbox cannot be established; never run unsandboxed."""


def _sandbox_command(command: list[str], workdir: str) -> list[str]:
    """Optionally confine a child using bubblewrap namespaces and a minimal root.

    The Docker playground opts into this mode explicitly. Local development
    stays on the historical resource-limited path unless opted in; there is
    no automatic downgrade when bubblewrap is requested but unavailable.
    """
    mode = os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX", "off")
    if mode == "off":
        return command
    if mode != "bwrap":
        raise SandboxUnavailable("Unsupported untrusted sandbox mode")
    binary = shutil.which("bwrap")
    if binary is None:
        raise SandboxUnavailable("Required bubblewrap sandbox is unavailable")

    args = [
        binary,
        "--unshare-user", "--unshare-pid", "--unshare-net",
        "--unshare-ipc", "--unshare-uts", "--disable-userns",
        "--cap-drop", "ALL",
        "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
    ]
    # Debian /bin and /lib* are often symlinks into /usr. Keep loader paths
    # without exposing host /etc, /root, /home, /opt, or the parent /tmp.
    for system_path in ("/bin", "/lib", "/lib64"):
        if os.path.islink(system_path):
            args += ["--symlink", os.readlink(system_path), system_path]
        elif os.path.isdir(system_path):
            args += ["--ro-bind", system_path, system_path]

    args += [
        "--dev", "/dev",
        "--proc", "/proc",
        "--dir", "/work",
        "--bind", workdir, "/work",
        "--size", str(16 * 1024 * 1024), "--tmpfs", "/tmp",
        "--chdir", "/work",
        "--clearenv",
    ]
    for key, value in _child_env().items():
        args += ["--setenv", key, value]
    args += ["--setenv", "HOME", "/work", "--", *command]
    return args


# Deployment-wide limits for the public Docker service. These are aggregate
# cgroup ceilings, independent of each interpreter's RLIMIT_* controls.
MAX_SERVICE_MEMORY_BYTES = 1536 * 1024 * 1024
MAX_SERVICE_PIDS = 128
MAX_SERVICE_CPU_CORES = 2


def require_container_limits(
    *,
    status_path: Path = Path("/proc/self/status"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> None:
    """Require an actually confined service when the hosted mode is enabled.

    Docker/Compose settings are declarations, not proof that the host applied
    them. Refuse to serve if the live process lacks syscall filtering,
    no-new-privileges, or finite cgroup-v2 CPU/memory/PID ceilings.
    """
    mode = os.environ.get("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "0")
    if mode == "0":
        return  # Explicit local-development compatibility mode.
    if mode != "1":
        raise SandboxUnavailable("Invalid container limits configuration")

    try:
        entries = dict(
            line.split(":", 1)
            for line in status_path.read_text(encoding="ascii").splitlines()
            if ":" in line
        )
        if entries["Seccomp"].strip() != "2":
            raise ValueError("seccomp filter is inactive")
        if entries["NoNewPrivs"].strip() != "1":
            raise ValueError("no_new_privs is inactive")

        def positive_bounded(path: str, maximum: int) -> int:
            value = (cgroup_root / path).read_text(encoding="ascii").strip()
            if not value.isdecimal():
                raise ValueError(f"{path} must be a finite integer")
            parsed = int(value)
            if not 0 < parsed <= maximum:
                raise ValueError(f"{path} is above the deployment limit")
            return parsed

        positive_bounded("memory.max", MAX_SERVICE_MEMORY_BYTES)
        positive_bounded("pids.max", MAX_SERVICE_PIDS)
        cpu = (cgroup_root / "cpu.max").read_text(encoding="ascii").split()
        if len(cpu) != 2 or not all(part.isdecimal() for part in cpu):
            raise ValueError("cpu.max must contain a finite quota and period")
        quota, period = (int(item) for item in cpu)
        if period <= 0 or quota <= 0 or quota > MAX_SERVICE_CPU_CORES * period:
            raise ValueError("cpu.max exceeds the deployment CPU quota")
    except (OSError, KeyError, ValueError) as error:
        raise SandboxUnavailable(
            "Required container seccomp/no-new-privileges/cgroup limits are unavailable"
        ) from error


def require_sandbox_ready() -> None:
    """Fail startup if the configured public-program sandbox cannot operate."""
    if os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX", "off") == "off":
        return

    with tempfile.TemporaryDirectory(prefix="ks-sandbox-preflight-") as workdir:
        # Compare namespace identities to the parent, not merely the
        # requested bubblewrap flags. Mount and network confinement are both
        # mandatory; an ignored or disabled unshare must refuse startup.
        parent_net = os.readlink("/proc/self/ns/net")
        parent_mnt = os.readlink("/proc/self/ns/mnt")
        probe = (
            "import os; "
            "assert os.getcwd() == '/work'; "
            "assert not os.path.exists('/etc/passwd'); "
            "print('KOSCHEI_SANDBOX_READY', "
            "os.readlink('/proc/self/ns/net'), "
            "os.readlink('/proc/self/ns/mnt'))"
        )
        command = _sandbox_command([sys.executable, "-c", probe], workdir)
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                env=_child_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                preexec_fn=_limit_child,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SandboxUnavailable("OS sandbox preflight failed") from error
        parts = completed.stdout.decode("ascii", "replace").strip().split()
        if (
            completed.returncode != 0
            or len(parts) != 3
            or parts[0] != "KOSCHEI_SANDBOX_READY"
            or parts[1] == parent_net
            or parts[2] == parent_mnt
        ):
            raise SandboxUnavailable("OS sandbox preflight failed; refusing to start")


def truncate(text: str) -> str:
    data = text.encode("utf-8", "replace")
    if len(data) <= MAX_OUTPUT_BYTES:
        return text
    return data[:MAX_OUTPUT_BYTES].decode("utf-8", "ignore") + "\n… output truncated"


def _bounded_output(stream, workdir: str) -> str:
    """Read at most one display window from file-backed subprocess output."""
    stream.seek(0)
    data = stream.read(MAX_OUTPUT_BYTES + 1)
    over_limit = len(data) > MAX_OUTPUT_BYTES
    text = (
        data[:MAX_OUTPUT_BYTES].decode("utf-8", "ignore")
        if over_limit
        else data.decode("utf-8", "replace")
    )
    # Do not reveal the temporary directory used for compilation.
    clean = text.replace(workdir + os.sep, "").replace(workdir, ".")
    clean = truncate(clean)
    if over_limit and not clean.endswith("output truncated"):
        clean += "\n… output truncated"
    return clean


def _ks(args: list[str], workdir: str) -> dict:
    # communicate() buffers *all* output in memory before truncation. Capturing
    # into anonymous temporary files avoids that untrusted allocation. Each
    # child's RLIMIT_FSIZE bounds each underlying file to 1 MiB.
    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
        process = subprocess.Popen(
            _sandbox_command(KS + args, workdir),
            cwd=workdir,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            preexec_fn=_limit_child,
        )
        try:
            process.wait(timeout=WALL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # _limit_child starts a new session; stop the whole process group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            return {
                "exit_code": None,
                "stdout": "",
                "stderr": f"Stopped: the program exceeded the {WALL_TIMEOUT_SECONDS}s time limit.",
                "timed_out": True,
            }
        return {
            "exit_code": process.returncode,
            "stdout": _bounded_output(stdout_file, workdir),
            "stderr": _bounded_output(stderr_file, workdir),
            "timed_out": False,
        }

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
