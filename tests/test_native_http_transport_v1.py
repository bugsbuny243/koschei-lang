from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from koschei import cli_entry
from koschei.http_response_budget_v1 import HTTP_CONTENT_ENCODING_ERROR_V1
from koschei.native_http_transport_v1 import native_http_transport_guard_go_v1


def test_native_transport_guard_source_is_identity_only_and_fail_closed():
    source = native_http_transport_guard_go_v1()

    assert 'clone.Header.Set("Accept-Encoding", "identity")' in source
    assert "bounded.DisableCompression = true" in source
    assert 'encoding != "" && encoding != "identity"' in source
    assert "response.Uncompressed" in source
    assert HTTP_CONTENT_ENCODING_ERROR_V1 in source
    assert "__KOSCHEI_HTTP_CONTENT_ENCODING_ERROR_V1__" not in source


def test_http_runtime_detection_does_not_widen_pure_native_packages():
    assert cli_entry._go_source_uses_http_runtime('package main\n\nfunc main() {}\n') is False
    assert (
        cli_entry._go_source_uses_http_runtime(
            'package main\n\nimport "net/http"\n\nvar _ = http.MethodGet\nfunc main() {}\n'
        )
        is True
    )


def test_public_native_compile_writes_transport_guard_only_for_http_package(
    monkeypatch, tmp_path: Path
):
    observed: dict[str, str | bool] = {}

    monkeypatch.setattr(cli_entry.shutil, "which", lambda name: "/usr/bin/go")

    def fake_run(command, *, cwd, capture_output, text, **kwargs):
        directory = Path(cwd)
        observed["main"] = (directory / "main.go").read_text(encoding="utf-8")
        guard_path = directory / "http_transport_v1.go"
        observed["guard_exists"] = guard_path.exists()
        if guard_path.exists():
            observed["guard"] = guard_path.read_text(encoding="utf-8")
        observed["module"] = (directory / "go.mod").read_text(encoding="utf-8")
        observed["command"] = " ".join(str(item) for item in command)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli_entry.subprocess, "run", fake_run)

    target = tmp_path / "app"
    http_source = (
        'package main\n\nimport "net/http"\n\n'
        'var _ = http.MethodGet\n\nfunc main() {}\n'
    )
    result = cli_entry._compile_mir_go(http_source, target, "en")

    assert result == 0
    assert observed["main"] == http_source
    assert observed["guard_exists"] is True
    assert observed["guard"] == native_http_transport_guard_go_v1()
    assert "module koscheiprogram" in str(observed["module"])
    assert str(observed["command"]).endswith(f"build -o {target} .")


def test_public_native_compile_omits_transport_guard_for_pure_package(
    monkeypatch, tmp_path: Path
):
    observed: dict[str, bool] = {}

    monkeypatch.setattr(cli_entry.shutil, "which", lambda name: "/usr/bin/go")

    def fake_run(command, *, cwd, capture_output, text, **kwargs):
        directory = Path(cwd)
        observed["guard_exists"] = (directory / "http_transport_v1.go").exists()
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli_entry.subprocess, "run", fake_run)

    result = cli_entry._compile_mir_go(
        'package main\n\nfunc main() {}\n', tmp_path / "pure", "en"
    )

    assert result == 0
    assert observed["guard_exists"] is False
