"""Fail-closed service-level seccomp and cgroup-v2 admission checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from koschei import untrusted


@pytest.fixture()
def confined_host(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "1")
    status = tmp_path / "status"
    cg = tmp_path / "cgroup"
    cg.mkdir()
    status.write_text(
        "Name:\tpython\nNoNewPrivs:\t1\nSeccomp:\t2\n",
        encoding="ascii",
    )
    (cg / "memory.max").write_text(str(1536 * 1024 * 1024), encoding="ascii")
    (cg / "pids.max").write_text("128", encoding="ascii")
    (cg / "cpu.max").write_text("200000 100000", encoding="ascii")
    return status, cg


def test_finite_seccomp_cgroup_limits_admit(confined_host):
    status, cg = confined_host
    assert untrusted.require_container_limits(status_path=status, cgroup_root=cg) is None


@pytest.mark.parametrize(
    "file_name,value",
    [
        ("memory.max", "max"),
        ("memory.max", str(1536 * 1024 * 1024 + 1)),
        ("memory.max", "0"),
        ("pids.max", "max"),
        ("pids.max", "129"),
        ("pids.max", "0"),
        ("cpu.max", "max 100000"),
        ("cpu.max", "200001 100000"),
        ("cpu.max", "0 100000"),
        ("cpu.max", "100000 0"),
        ("cpu.max", "200000"),
    ],
)
def test_missing_or_weak_quota_denied(confined_host, file_name, value):
    status, cg = confined_host
    (cg / file_name).write_text(value, encoding="ascii")
    with pytest.raises(untrusted.SandboxUnavailable, match="Required container"):
        untrusted.require_container_limits(status_path=status, cgroup_root=cg)


@pytest.mark.parametrize(
    "status_body",
    [
        "NoNewPrivs:\t0\nSeccomp:\t2\n",
        "NoNewPrivs:\t1\nSeccomp:\t0\n",
        "NoNewPrivs:\t1\nSeccomp:\t1\n",
        "NoNewPrivs:\t1\n",
    ],
)
def test_missing_or_weak_process_security_denied(confined_host, status_body):
    status, cg = confined_host
    status.write_text(status_body, encoding="ascii")
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted.require_container_limits(status_path=status, cgroup_root=cg)


def test_missing_cgroup_v2_files_denied(confined_host):
    status, cg = confined_host
    (cg / "cpu.max").unlink()
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted.require_container_limits(status_path=status, cgroup_root=cg)


def test_unknown_deployment_setting_denied(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "yes")
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted.require_container_limits(
            status_path=tmp_path / "missing",
            cgroup_root=tmp_path,
        )


def test_opt_out_requires_explicit_local_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "0")
    untrusted.require_container_limits(
        status_path=tmp_path / "missing",
        cgroup_root=tmp_path / "missing-cgroup",
    )


def test_public_image_requires_kernel_limit_preflight():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "server/playground/Dockerfile").read_text(encoding="utf-8")
    server = (root / "server/playground/app.py").read_text(encoding="utf-8")
    compose = (root / "server/playground/compose.security.yaml").read_text(encoding="utf-8")

    assert "KOSCHEI_REQUIRE_CONTAINER_LIMITS=1" in dockerfile
    assert "untrusted.require_container_limits()" in server
    assert "no-new-privileges:true" in compose
    assert "mem_limit: 1536m" in compose
    assert "cpus: 2.0" in compose
    assert "pids_limit: 128" in compose
    assert "read_only: true" in compose
    assert "cap_drop:" in compose
    assert "seccomp:unconfined" not in compose
