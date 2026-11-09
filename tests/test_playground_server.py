"""Tests for the server-side Koschei playground (server/playground/app.py)."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parents[1] / "server" / "playground" / "app.py"
spec = importlib.util.spec_from_file_location("koschei_playground_app", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

HELLO = 'fn main() {\n    print("hello")\n}\n'
READ_ETC = (
    "fn main(caps: SystemCaps) {\n"
    '    let d = caps.disk.allow_read_only("/etc")\n'
    '    let s = d.read("/etc/hostname") or "none"\n'
    "    print(s)\n"
    "}\n"
)
READ_ENV = (
    "fn main(caps: SystemCaps) {\n"
    '    let e = caps.env.allow("HOME")\n'
    '    print(e.get("HOME") or "none")\n'
    "}\n"
)
LOOP = "fn main() {\n    let mut i = 0\n    while true {\n        i = i + 1\n    }\n}\n"


def test_pure_program_runs():
    result = app.evaluate(HELLO, "run")
    assert result["stage"] == "run" and result["ran"]
    assert result["run"]["exit_code"] == 0
    assert result["run"]["stdout"].strip() == "hello"
    assert result["manifest"]["has_capabilities"] is False


def test_narrowed_disk_access_is_blocked_before_running():
    result = app.evaluate(READ_ETC, "run")
    assert result["stage"] == "policy"
    assert result["ran"] is False and "run" not in result
    assert result["policy"]["exit_code"] == 2
    assert "denied capability domain requested: disk" in result["policy"]["stderr"]
    assert result["manifest"]["grants"][0]["scope"] == "/etc"


def test_environment_access_is_blocked():
    result = app.evaluate(READ_ENV, "run")
    assert result["stage"] == "policy" and not result["ran"]
    assert "env" in result["policy"]["stderr"]


def test_compile_error_is_reported_without_running():
    result = app.evaluate("fn main( {", "run")
    assert result["stage"] == "check" and not result["ran"]
    assert result["policy"]["exit_code"] == 1
    assert "KS1003" in result["policy"]["stderr"]


def test_check_only_does_not_run():
    result = app.evaluate(HELLO, "check")
    assert result["ran"] is False and result["policy"]["exit_code"] == 0


def test_infinite_loop_is_stopped():
    result = app.evaluate(LOOP, "run")
    assert result["ran"]
    assert result["run"]["exit_code"] != 0
    assert "KS3601" in result["run"]["stderr"] or result["run"]["timed_out"]


def test_temp_paths_are_not_leaked():
    result = app.evaluate("fn main( {", "run")
    assert "ks-playground-" not in result["policy"]["stderr"]


def test_invalid_action_rejected():
    with pytest.raises(ValueError):
        app.evaluate(HELLO, "build")


def test_output_truncation():
    text = "x" * (app.MAX_OUTPUT_BYTES + 100)
    assert app._truncate(text).endswith("output truncated")


def test_rate_limiter():
    limiter = app.RateLimiter(2, 60)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    app.LIMITER = app.RateLimiter(1000, 60)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, body: bytes) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_http_index_and_evaluate(server):
    with urllib.request.urlopen(server + "/", timeout=10) as response:
        assert response.status == 200
        assert b"Koschei Playground" in response.read()
    status, data = _post(server + "/api/evaluate", json.dumps({"source": HELLO, "action": "run"}).encode())
    assert status == 200 and data["run"]["stdout"].strip() == "hello"


def test_http_rejects_oversized_source(server):
    big = json.dumps({"source": "x" * (app.MAX_SOURCE_BYTES + 10)}).encode()
    status, data = _post(server + "/api/evaluate", big)
    assert status in (400, 413)


def test_http_rejects_bad_json(server):
    status, data = _post(server + "/api/evaluate", b"not json")
    assert status == 400 and data["error"] == "invalid_request"
