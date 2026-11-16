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
    monkeypatch.setattr(worker, "ThreadingHTTPServer", lambda *a: pytest.fail("listener created"))
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
