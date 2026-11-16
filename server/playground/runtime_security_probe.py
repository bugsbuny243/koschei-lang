"""Live security probe for the hardened Playground container.

On a VM it is the worker unit's ExecStartPre (server/playground/vm): it runs
with exactly the service's confinement, and the worker does not start unless
every check passes.

This is a *deployment acceptance probe*, not a substitute for an audit.
All checks fail closed. It does not access external networks or host secrets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from koschei import untrusted


def check(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError("PLAYGROUND ISOLATION DENIED: " + reason)


def _own_cgroup(cgroup: Path) -> Path:
    try:
        return untrusted.own_cgroup_dir(cgroup_root=cgroup)
    except (OSError, ValueError):
        return cgroup


def host_security_snapshot(proc: Path = Path("/proc"), cgroup: Path = Path("/sys/fs/cgroup")) -> dict:
    """Allowlisted, bounded evidence only; never dump environment or host files.

    Seccomp mode is not the filter itself. These observations cannot identify
    which of seccomp, an LSM, or a kernel namespace restriction denied bwrap.
    Missing evidence is reported as unknown, never as proof of compatibility.
    """
    def read(path: Path) -> str | None:
        try:
            with path.open(encoding="ascii", errors="replace") as stream:
                return stream.read(4096).strip()
        except OSError:
            return None

    status = read(proc / "self/status") or ""
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    return {
        "process": {key: fields.get(key, "unknown").strip() for key in (
            "Seccomp", "Seccomp_filters", "NoNewPrivs", "CapEff",
        )},
        "namespace_controls": {name: read(proc / path) for name, path in {
            "max_user_namespaces": "sys/user/max_user_namespaces",
            "unprivileged_userns_clone": "sys/kernel/unprivileged_userns_clone",
            "apparmor_restrict_unprivileged_userns": "sys/kernel/apparmor_restrict_unprivileged_userns",
        }.items()},
        "cgroup": {name: read(_own_cgroup(cgroup) / name) for name in (
            "memory.max", "cpu.max", "pids.max",
        )},
        "denial_source": "undetermined: inspect effective seccomp and LSM policies on the host",
    }


def report_host_security() -> None:
    print("HOST_SECURITY: " + json.dumps(host_security_snapshot(), sort_keys=True), file=sys.stderr)


def report_bubblewrap_diagnostic() -> None:
    """Capture a minimal, non-secret namespace-launch failure reason."""
    with tempfile.TemporaryDirectory(prefix="ks-diagnostic-") as root:
        command = untrusted._sandbox_command(
            [sys.executable, "-c", "print('BWRAP_EXEC_OK')"], root
        )
        try:
            result = subprocess.run(
                command,
                cwd=root,
                env=untrusted._child_env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=5,
                preexec_fn=untrusted._limit_child,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                "BWRAP_DIAGNOSTIC: launch failed (" + type(exc).__name__ + ")",
                file=sys.stderr,
            )
            return
        # This is intentionally limited to the sandbox tool's diagnostic;
        # never log the untrusted program or user-submitted source.
        details = result.stderr.decode("utf-8", "replace")[:500].strip()
        print(
            f"BWRAP_DIAGNOSTIC: exit={result.returncode} stderr={details!r}",
            file=sys.stderr,
        )


def isolated_probe() -> None:
    # Verify the intended parent service has kernel-enforced resource limits
    # and the child launcher passes its startup namespace requirements.
    check(os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX") == "bwrap", "sandbox disabled")
    check(os.environ.get("KOSCHEI_REQUIRE_CONTAINER_LIMITS") == "1", "cgroup check disabled")
    report_host_security()
    untrusted.require_container_limits()
    try:
        untrusted.require_sandbox_ready()
    except untrusted.SandboxUnavailable:
        report_bubblewrap_diagnostic()
        raise

    # A listening socket in the *parent* network namespace should be
    # unreachable from the child. Loopback avoids external network probes.
    parent_pid_ns = os.readlink("/proc/self/ns/pid")
    secrets_dir = os.environ.get("CREDENTIALS_DIRECTORY", "")
    own_source = str(Path(__file__).resolve())
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(1)
        port = listener.getsockname()[1]

        with tempfile.TemporaryDirectory(prefix="ks-live-security-") as root:
            root_path = Path(root)
            # A marker outside the bound /work must not be visible to the child.
            with tempfile.TemporaryDirectory(prefix="ks-host-private-") as private:
                secret = Path(private) / "isolation-marker.txt"
                secret.write_text("NOT_VISIBLE", encoding="utf-8")
                probe = (
                    "import os,socket,sys;"
                    "assert os.getcwd() == '/work';"
                    "assert not os.path.exists('/etc/passwd');"
                    "assert not os.path.exists('/opt/playground/app.py');"
                    "assert not os.path.exists(" + repr(own_source) + ");"
                    "assert not os.path.exists(" + repr(str(secret)) + ");"
                    # The worker's credentials never reach the program.
                    "assert " + repr(secrets_dir) + " == '' or not os.path.exists(" + repr(secrets_dir) + ");"
                    "assert not any('TOKEN' in k or 'CREDENTIAL' in k for k in os.environ);"
                    # Own PID namespace: only the sandbox's processes exist.
                    "assert os.readlink('/proc/self/ns/pid') != " + repr(parent_pid_ns) + ";"
                    "pids=[d for d in os.listdir('/proc') if d.isdigit()];"
                    "assert len(pids) <= 3, pids;"
                    "p=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
                    "p.settimeout(1);"
                    "blocked=False;"
                    "\ntry:\n"
                    " p.connect(('127.0.0.1'," + str(port) + "))\n"
                    "except OSError:\n blocked=True\n"
                    "finally:\n p.close()\n"
                    "assert blocked, 'parent loopback reached from child';"
                    "print('ISOLATION_OK')"
                )
                command = untrusted._sandbox_command([sys.executable, "-c", probe], str(root_path))
                result = subprocess.run(
                    command,
                    cwd=root,
                    env=untrusted._child_env(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=untrusted.WALL_TIMEOUT_SECONDS,
                    preexec_fn=untrusted._limit_child,
                )
                check(
                    result.returncode == 0 and result.stdout == b"ISOLATION_OK\n",
                    "child filesystem/network/pid/secret isolation probe failed: "
                    + result.stderr.decode("utf-8", "replace")[-300:],
                )

    # Per-program limits are enforced by the kernel, not just requested.
    with tempfile.TemporaryDirectory(prefix="ks-limits-") as root:
        def sandboxed(code: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                untrusted._sandbox_command([sys.executable, "-c", code], root),
                cwd=root, env=untrusted._child_env(), stdin=subprocess.DEVNULL,
                capture_output=True, timeout=untrusted.WALL_TIMEOUT_SECONDS + 5,
                preexec_fn=untrusted._limit_child,
            )
        memory = sandboxed("b=bytearray(%d); print('ALLOCATED')" % (untrusted.MEMORY_BYTES + 64 * 1024 * 1024))
        check(b"ALLOCATED" not in memory.stdout and memory.returncode != 0, "memory limit not enforced")
        cpu = sandboxed("while True: pass")
        check(cpu.returncode != 0, "CPU limit not enforced")
        big = sandboxed("open('big','wb').write(b'x' * %d); print('WROTE')" % (4 * 1024 * 1024))
        check(b"WROTE" not in big.stdout, "file size limit not enforced")
    # Prove that both policy checking and actual .ks execution still work.
    allowed = untrusted.evaluate('fn main() { println("playground-ok") }\n', "run")
    check(
        allowed.get("stage") == "run"
        and allowed.get("ran") is True
        and allowed["run"]["exit_code"] == 0
        and allowed["run"]["stdout"].strip() == "playground-ok",
        "sandboxed Koschei program failed to execute",
    )
    blocked = untrusted.evaluate(
        'fn main(caps: SystemCaps) {\n'
        ' let disk = caps.disk.allow_read_only("/etc")\n'
        ' println(disk.read("/etc/passwd"))\n'
        '}\n',
        "run",
    )
    check(
        blocked.get("stage") == "policy"
        and blocked.get("ran") is False,
        "capability denial failed",
    )
    print(json.dumps({"result": "PASS", "checks": [
        "cgroups", "seccomp", "no_new_privs", "namespace_preflight",
        "child_filesystem", "child_loopback_network", "child_pid_namespace",
        "worker_secrets_hidden", "memory_limit", "cpu_limit", "file_size_limit",
        "koschei_run", "capability_deny",
    ]}, sort_keys=True))


if __name__ == "__main__":
    isolated_probe()
