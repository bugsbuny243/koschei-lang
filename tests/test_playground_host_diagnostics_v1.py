"""Deployment diagnostics must remain bounded, non-secret and fail closed."""

import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "server/playground/runtime_security_probe.py"
spec = importlib.util.spec_from_file_location("playground_runtime_probe", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_snapshot_only_reports_allowlisted_evidence(tmp_path):
    proc, cg = tmp_path / "proc", tmp_path / "cgroup"
    (proc / "self").mkdir(parents=True)
    cg.mkdir()
    (proc / "self/status").write_text(
        "Name:\tSECRET_NAME\nSeccomp:\t2\nNoNewPrivs:\t1\nCapEff:\t0000\n"
    )
    (proc / "self/environ").write_text("TOKEN=SECRET_TOKEN")
    (cg / "memory.max").write_text("1610612736\n")
    snapshot = probe.host_security_snapshot(proc, cg)
    assert snapshot["process"]["Seccomp"] == "2"
    assert snapshot["cgroup"]["memory.max"] == "1610612736"
    assert snapshot["process"]["Seccomp_filters"] == "unknown"
    assert "SECRET" not in json.dumps(snapshot)
    assert snapshot["denial_source"].startswith("undetermined")


def test_missing_host_controls_are_unknown_not_success(tmp_path):
    snapshot = probe.host_security_snapshot(tmp_path, tmp_path)
    assert set(snapshot["process"].values()) == {"unknown"}
    assert set(snapshot["namespace_controls"].values()) == {None}
    assert set(snapshot["cgroup"].values()) == {None}


def test_evidence_read_is_bounded(tmp_path):
    (tmp_path / "memory.max").write_text("9" * 100_000)
    snapshot = probe.host_security_snapshot(tmp_path, tmp_path)
    assert len(snapshot["cgroup"]["memory.max"]) == 4096


@pytest.mark.parametrize("failure_stage", ["container", "namespace"])
def test_diagnostics_do_not_turn_admission_failure_into_success(monkeypatch, failure_stage):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setenv("KOSCHEI_REQUIRE_CONTAINER_LIMITS", "1")
    events = []
    monkeypatch.setattr(probe, "report_host_security", lambda: events.append("host"))
    monkeypatch.setattr(probe, "report_bubblewrap_diagnostic", lambda: events.append("bwrap"))

    def gate(stage):
        events.append(stage)
        if stage == failure_stage:
            raise probe.untrusted.SandboxUnavailable("denied")

    monkeypatch.setattr(probe.untrusted, "require_container_limits", lambda: gate("container"))
    monkeypatch.setattr(probe.untrusted, "require_sandbox_ready", lambda: gate("namespace"))
    with pytest.raises(probe.untrusted.SandboxUnavailable, match="denied"):
        probe.isolated_probe()
    assert events == (["host", "container"] if failure_stage == "container" else
                      ["host", "container", "namespace", "bwrap"])
