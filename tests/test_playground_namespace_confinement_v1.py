"""Security checks for the optional Linux namespace sandbox launcher.

These unit tests validate fail-closed configuration and the launch contract.
A successful real bubblewrap mount/network/PID isolation smoke test still
requires a CI runner that permits unprivileged user namespaces.
"""

from __future__ import annotations

import sys

import pytest

from koschei import untrusted


def test_bwrap_command_has_separate_network_and_minimal_filesystem(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setattr(untrusted.shutil, "which", lambda command: "/usr/bin/bwrap")

    child = [sys.executable, "-m", "koschei", "version"]
    command = untrusted._sandbox_command(child, str(tmp_path))

    assert command[0] == "/usr/bin/bwrap"
    for flag in (
        "--unshare-user", "--unshare-pid", "--unshare-net",
        "--unshare-ipc", "--unshare-uts", "--disable-userns",
        "--die-with-parent",
        "--clearenv",
    ):
        assert flag in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop"):command.index("--cap-drop") + 2
    ]
    assert command[command.index("--ro-bind"):command.index("--ro-bind") + 3] == [
        "--ro-bind", "/usr", "/usr",
    ]
    assert command[command.index("--bind"):command.index("--bind") + 3] == [
        "--bind", str(tmp_path), "/work",
    ]
    assert command[command.index("--tmpfs"):command.index("--tmpfs") + 2] == [
        "--tmpfs", "/tmp",
    ]
    assert command[command.index("--size"):command.index("--size") + 2] == [
        "--size", str(16 * 1024 * 1024),
    ]
    assert command[-len(child) - 1:] == ["--", *child]
    assert not any(
        command[index:index + 3] == ["--ro-bind", "/", "/"]
        for index in range(len(command) - 2)
    )


def test_requested_sandbox_never_falls_back_to_direct_launch(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setattr(untrusted.shutil, "which", lambda command: None)

    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted._sandbox_command(["/usr/bin/python3", "-c", "pass"], str(tmp_path))
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted._ks(["version"], str(tmp_path))
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted.require_sandbox_ready()


def test_unknown_sandbox_configuration_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "broken")
    with pytest.raises(untrusted.SandboxUnavailable):
        untrusted._sandbox_command([sys.executable], str(tmp_path))


def test_local_explicit_off_mode_preserves_cli_compatibility(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "off")
    command = [sys.executable, "-c", "pass"]
    assert untrusted._sandbox_command(command, str(tmp_path)) is command
    untrusted.require_sandbox_ready()


def test_preflight_rejects_unsandboxed_or_wrong_response(monkeypatch, tmp_path):
    monkeypatch.setenv("KOSCHEI_UNTRUSTED_SANDBOX", "bwrap")
    monkeypatch.setattr(
        untrusted,
        "_sandbox_command",
        lambda child, workdir: [sys.executable, "-c", "print('WRONG')"],
    )
    with pytest.raises(untrusted.SandboxUnavailable, match="preflight failed"):
        untrusted.require_sandbox_ready()


def test_hosted_playground_enforces_preflight_at_startup():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    dockerfile = (root / "server/playground/Dockerfile").read_text()
    app = (root / "server/playground/app.py").read_text()
    assert "KOSCHEI_UNTRUSTED_SANDBOX=bwrap" in dockerfile
    assert "untrusted.require_sandbox_ready()" in app
