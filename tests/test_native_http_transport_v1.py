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


def test_public_native_compile_writes_transport_guard_into_go_package(
    monkeypatch, tmp_path: Path
):
    observed: dict[str, str] = {}

    monkeypatch.setattr(cli_entry.shutil, "which", lambda name: "/usr/bin/go")

    def fake_run(command, *, cwd, capture_output, text, **kwargs):
        directory = Path(cwd)
        observed["main"] = (directory / "main.go").read_text(encoding="utf-8")
        observed["guard"] = (directory / "http_transport_v1.go").read_text(
            encoding="utf-8"
        )
        observed["module"] = (directory / "go.mod").read_text(encoding="utf-8")
        observed["command"] = " ".join(str(item) for item in command)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli_entry.subprocess, "run", fake_run)

    target = tmp_path / "app"
    result = cli_entry._compile_mir_go(
        'package main\n\nfunc main() {}\n', target, "en"
    )

    assert result == 0
    assert observed["main"] == 'package main\n\nfunc main() {}\n'
    assert observed["guard"] == native_http_transport_guard_go_v1()
    assert "module koscheiprogram" in observed["module"]
    assert observed["command"].endswith(f"build -o {target} .")
