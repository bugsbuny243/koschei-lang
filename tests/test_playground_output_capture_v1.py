"""Regression tests for file-backed, bounded untrusted subprocess capture."""

from __future__ import annotations

import sys

from koschei import untrusted


def test_large_stdout_and_stderr_are_bounded(monkeypatch, tmp_path) -> None:
    script = (
        "import sys\n"
        "sys.stdout.write('x' * 150_000)\n"
        "sys.stderr.write('y' * 150_000)\n"
    )
    monkeypatch.setattr(untrusted, "KS", [sys.executable, "-c", script])

    result = untrusted._ks([], str(tmp_path))

    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    for stream, expected in (("stdout", "x"), ("stderr", "y")):
        value = result[stream]
        assert value.startswith(expected)
        assert value.endswith("output truncated")
        assert len(value.encode("utf-8")) <= untrusted.MAX_OUTPUT_BYTES + 64


def test_captured_output_redacts_the_work_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        untrusted, "KS", [sys.executable, "-c", "import os; print(os.getcwd())"]
    )

    result = untrusted._ks([], str(tmp_path))

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "."
    assert str(tmp_path) not in result["stdout"]


def test_timeout_stops_child_process(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        untrusted, "KS", [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    monkeypatch.setattr(untrusted, "WALL_TIMEOUT_SECONDS", 0.2)

    result = untrusted._ks([], str(tmp_path))

    assert result["timed_out"] is True
    assert result["exit_code"] is None
    assert "time limit" in result["stderr"]
