"""Live security probe for the hardened Playground container.

Run only inside the explicitly locked-down Docker Compose service:
    docker compose -f server/playground/compose.security.yaml run --rm \\
        --no-deps -T playground python /opt/playground/runtime_security_probe.py

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


def isolated_probe() -> None:
    # Verify the intended parent service has kernel-enforced resource limits
    # and the child launcher passes its startup namespace requirements.
    check(os.environ.get("KOSCHEI_UNTRUSTED_SANDBOX") == "bwrap", "sandbox disabled")
    check(os.environ.get("KOSCHEI_REQUIRE_CONTAINER_LIMITS") == "1", "cgroup check disabled")
    untrusted.require_container_limits()
    untrusted.require_sandbox_ready()

    # A listening socket in the *parent* network namespace should be
    # unreachable from the child. Loopback avoids external network probes.
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
                    "assert not os.path.exists(" + repr(str(secret)) + ");"
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
                    result.returncode == 0 and result.stdout == b"ISOLATION_OK\\n",
                    "child filesystem/network isolation probe failed",
                )

    # Prove that both policy checking and actual .ks execution still work.
    allowed = untrusted.evaluate('fn main() { println("playground-ok") }\\n', "run")
    check(
        allowed.get("stage") == "run"
        and allowed.get("ran") is True
        and allowed["run"]["exit_code"] == 0
        and allowed["run"]["stdout"].strip() == "playground-ok",
        "sandboxed Koschei program failed to execute",
    )
    blocked = untrusted.evaluate(
        'fn main(caps: SystemCaps) {\\n'
        ' let disk = caps.disk.allow_read_only("/etc")\\n'
        ' println(disk.read("/etc/passwd"))\\n'
        '}\\n',
        "run",
    )
    check(
        blocked.get("stage") == "policy"
        and blocked.get("ran") is False,
        "capability denial failed",
    )
    print(json.dumps({"result": "PASS", "checks": [
        "cgroups", "seccomp", "no_new_privs", "namespace_preflight",
        "child_filesystem", "child_loopback_network", "koschei_run", "capability_deny",
    ]}, sort_keys=True))


if __name__ == "__main__":
    isolated_probe()
