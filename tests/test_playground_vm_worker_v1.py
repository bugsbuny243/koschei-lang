"""VM worker configuration rules (unit level; the VM acceptance runs are in
server/playground/vm/test and are not reproduced here)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from koschei import untrusted
from server.playground import app, worker

TOKEN = "b" * 64
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", ["0", "-1", "abc", "181", "1.5", " 5"])
def test_time_limit_overrides_are_bounded(monkeypatch, value):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_WALL_SECONDS", value)
    with pytest.raises(ValueError):
        untrusted._bounded_seconds("KOSCHEI_UNTRUSTED_WALL_SECONDS", 10, 180)


def test_time_limit_defaults_and_valid_override(monkeypatch):
    monkeypatch.delenv("KOSCHEI_UNTRUSTED_CPU_SECONDS", raising=False)
    assert untrusted._bounded_seconds("KOSCHEI_UNTRUSTED_CPU_SECONDS", 5, 120) == 5
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_CPU_SECONDS", "60")
    assert untrusted._bounded_seconds("KOSCHEI_UNTRUSTED_CPU_SECONDS", 5, 120) == 60


@pytest.mark.parametrize("path", ["bwrap", "/nonexistent/bwrap", "/etc/hostname"])
def test_explicit_bubblewrap_must_be_an_absolute_executable(monkeypatch, path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_BWRAP", path)
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted._sandbox_command(["true"], "/tmp")


def test_venv_outside_usr_is_bound_read_only(monkeypatch, tmp_path):
    fake = tmp_path / "bwrap"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_BWRAP", str(fake))
    monkeypatch.setattr(sys, "prefix", "/opt/koschei-worker/venv")
    monkeypatch.setattr(os.path, "realpath", lambda p: p)
    args = untrusted._sandbox_command(["python"], "/tmp/w")
    assert args[0] == str(fake)
    index = args.index("/opt/koschei-worker/venv")
    assert args[index - 1] == "--ro-bind" and args[index + 1] == "/opt/koschei-worker/venv"
    assert "--bind" not in args[:index]  # never writable


def test_worker_secrets_come_from_the_credential_directory(monkeypatch, tmp_path):
    (tmp_path / "worker-token").write_text(TOKEN + "\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", "c" * 64)
    assert worker._secret("worker-token", "KOSCHEI_WORKER_TOKEN") == TOKEN


@pytest.mark.parametrize("bind", ["0.0.0.0", "10.0.0.5"])
def test_non_loopback_worker_requires_tls(monkeypatch, bind):
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("KOSCHEI_WORKER_TLS_CERT", raising=False)
    monkeypatch.delenv("KOSCHEI_WORKER_TLS_KEY", raising=False)
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "1")
    monkeypatch.setenv("KOSCHEI_WORKER_BIND", bind)
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    monkeypatch.setattr(worker, "WorkerServer", lambda *a, **k: pytest.fail("listener created"))
    with pytest.raises(untrusted.SandboxUnavailable):
        worker.main()


def test_half_configured_tls_is_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setenv("KOSCHEI_WORKER_TLS_CERT", str(tmp_path / "cert.pem"))
    monkeypatch.delenv("KOSCHEI_WORKER_TLS_KEY", raising=False)
    with pytest.raises(untrusted.SandboxUnavailable):
        worker.tls_context()


def test_unit_keeps_mandatory_confinement():
    unit = (ROOT / "server/playground/vm/koschei-worker.service").read_text()
    for line in ("NoNewPrivileges=yes", "CapabilityBoundingSet=\n", "SystemCallFilter=@system-service @mount",
                 "RestrictNamespaces=user mnt pid net ipc uts", "IPAddressDeny=any", "MemoryMax=", "TasksMax=",
                 "CPUQuota=", "LoadCredential=worker-token:", "ExecStartPre=", "runtime_security_probe.py",
                 "KOSCHEI_REQUIRE_CONTAINER_LIMITS=1", "KOSCHEI_UNTRUSTED_SANDBOX=bwrap"):
        assert line in unit, line
    for forbidden in ("seccomp=unconfined", "--privileged", "CAP_SYS_ADMIN", "KOSCHEI_WORKER_TOKEN=",
                      "KOSCHEI_UNTRUSTED_CPU_SECONDS", "KOSCHEI_UNTRUSTED_WALL_SECONDS"):
        assert forbidden not in unit, forbidden
    profile = (ROOT / "server/playground/vm/koschei-bwrap.apparmor").read_text()
    assert "profile koschei-bwrap /opt/koschei-worker/bin/bwrap" in profile and "userns," in profile


# --- Ingress / egress split (koschei-worker.socket) -------------------------

def _service_network_lines():
    unit = (ROOT / "server/playground/vm/koschei-worker.service").read_text()
    return [l.strip() for l in unit.splitlines() if l.startswith(("IPAddressAllow", "IPAddressDeny"))]


def test_service_egress_is_loopback_only_and_ingress_lives_on_the_socket():
    assert _service_network_lines() == ["IPAddressDeny=any", "IPAddressAllow=localhost"]
    unit = (ROOT / "server/playground/vm/koschei-worker.service").read_text()
    assert "Requires=koschei-worker.socket" in unit
    socket_unit = (ROOT / "server/playground/vm/koschei-worker.socket").read_text()
    assert "IPAddressDeny=any" in socket_unit and "Accept=no" in socket_unit
    # The default ingress is never written into a unit file shipped in the repo.
    assert "IPAddressAllow=any" not in socket_unit


def test_installer_never_widens_the_service_and_checks_it():
    script = (ROOT / "server/playground/vm/install.sh").read_text()
    assert "koschei-worker.service.d/peer.conf" in script and "rm -f" in script
    assert "[Service]\\nIPAddressAllow" not in script
    assert "koschei-worker.socket.d/ingress.conf" in script
    assert "systemctl show -p IPAddressAllow --value koschei-worker.service" in script
    assert "worker egress is not loopback-only; refusing" in script


def test_activated_socket_absent_without_systemd(monkeypatch):
    monkeypatch.delenv("LISTEN_PID", raising=False)
    assert worker.activated_socket() is None
    monkeypatch.setenv("LISTEN_PID", "1")  # someone else's descriptors
    monkeypatch.setenv("LISTEN_FDS", "1")
    assert worker.activated_socket() is None


def test_activated_socket_must_be_exactly_one(monkeypatch):
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "2")
    with pytest.raises(untrusted.SandboxUnavailable):
        worker.activated_socket()


def test_activated_tcp_listener_is_adopted_non_inheritable(monkeypatch):
    import socket
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    saved = os.dup(worker.SD_LISTEN_FDS_START)
    try:
        os.dup2(listener.fileno(), worker.SD_LISTEN_FDS_START, inheritable=True)
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setenv("LISTEN_FDS", "1")
        adopted = worker.activated_socket()
        assert adopted.getsockname() == listener.getsockname()
        assert not adopted.get_inheritable()
        assert "LISTEN_FDS" not in os.environ and "LISTEN_PID" not in os.environ
        adopted.detach()
    finally:
        os.dup2(saved, worker.SD_LISTEN_FDS_START)
        os.close(saved)
        listener.close()


def test_activated_udp_socket_is_refused(monkeypatch):
    import socket
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    saved = os.dup(worker.SD_LISTEN_FDS_START)
    try:
        os.dup2(udp.fileno(), worker.SD_LISTEN_FDS_START)
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setenv("LISTEN_FDS", "1")
        with pytest.raises(untrusted.SandboxUnavailable):
            worker.activated_socket()
    finally:
        os.dup2(saved, worker.SD_LISTEN_FDS_START)
        os.close(saved)
        udp.close()


def test_socket_activated_worker_without_tls_is_refused(monkeypatch):
    import socket
    monkeypatch.setenv("KOSCHEI_WORKER_TOKEN", TOKEN)
    for name in ("CREDENTIALS_DIRECTORY", "KOSCHEI_WORKER_TLS_CERT", "KOSCHEI_WORKER_TLS_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "1")
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "enabled")
    loop = socket.socket()
    loop.bind(("127.0.0.1", 0))  # even a loopback socket from systemd needs TLS
    monkeypatch.setattr(worker, "activated_socket", lambda: loop)
    monkeypatch.setattr(worker, "WorkerServer", lambda *a, **k: pytest.fail("listener served"))
    try:
        with pytest.raises(untrusted.SandboxUnavailable):
            worker.main()
    finally:
        loop.close()


# --- Probe: sandboxed programs have no network --------------------------------

from server.playground import runtime_security_probe as probe  # noqa: E402


def _run_probe_code(code):
    import subprocess
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)


def test_network_probe_detects_a_reachable_destination():
    """Outside a sandbox the probe must fail: it really connects and checks."""
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        result = _run_probe_code(probe.child_network_probe([listener.getsockname()]))
    assert result.returncode != 0 and "NETWORK_OK" not in result.stdout


def test_descriptor_probe_detects_an_inherited_descriptor():
    import subprocess
    r, w = os.pipe()
    try:
        result = subprocess.run([sys.executable, "-c", probe.CHILD_DESCRIPTOR_PROBE],
                                pass_fds=(r,), capture_output=True, text=True, timeout=60)
    finally:
        os.close(r)
        os.close(w)
    assert result.returncode != 0 and "DESCRIPTORS_OK" not in result.stdout
    clean = subprocess.run([sys.executable, "-c", probe.CHILD_DESCRIPTOR_PROBE],
                           capture_output=True, text=True, timeout=60)
    assert clean.stdout == "DESCRIPTORS_OK\n"


def test_host_destinations_reads_the_default_gateway(tmp_path):
    table = tmp_path / "route"
    table.write_text(
        "Iface\tDestination\tGateway \tFlags\n"
        "eth0\t00000000\t0202000A\t0003\n"
        "eth0\t0002000A\t00000000\t0001\n")
    assert ("10.0.2.2", 80) in probe.host_destinations(table)


def test_forbidden_destinations_cover_internet_metadata_and_private_ranges():
    import ipaddress
    hosts = [ipaddress.ip_address(h) for h, _ in probe.FORBIDDEN_DESTINATIONS]
    assert any(h.version == 6 and h.is_global for h in hosts)
    assert any(h.version == 4 and h.is_global for h in hosts)
    assert ipaddress.ip_address("169.254.169.254") in hosts
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"):
        assert any(h in ipaddress.ip_network(net) for h in hosts), net
