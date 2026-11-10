"""Tests for the Koschei MCP server (koschei/mcp_server.py)."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys

import pytest

from koschei import mcp_server, untrusted

HELLO = 'fn main() {\n    println("hello")\n}\n'
READ_DATA = (
    "fn main(caps: SystemCaps) {\n"
    '    let data = caps.disk.allow_read_only("/data")\n'
    '    let text = data.read("/data/input.txt") or "missing"\n'
    "    println(text)\n"
    "}\n"
)
FETCH = (
    "fn main(caps: SystemCaps) {\n"
    '    let api = caps.net.allow("https://collector.example.com")\n'
    '    println(api.get("https://collector.example.com/x") or "failed")\n'
    "}\n"
)


def call(server, name, **arguments):
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    return response["result"]


def test_initialize_and_tool_list():
    server = mcp_server.Server()
    init = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})["result"]
    assert init["capabilities"] == {"tools": {}}
    assert init["serverInfo"]["name"] == "koschei"
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["koschei_guide", "koschei_check", "koschei_run"]
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)


def test_pure_program_runs_by_default():
    result = call(mcp_server.Server(), "koschei_run", source=HELLO)
    assert result["isError"] is False
    assert result["structuredContent"]["outcome"] == "ok"
    assert result["structuredContent"]["stdout"] == "hello\n"
    assert "Requests no capabilities" in result["content"][0]["text"]


def test_default_policy_blocks_disk_before_running():
    result = call(mcp_server.Server(), "koschei_run", source=READ_DATA)
    data = result["structuredContent"]
    assert result["isError"] is True
    assert data["outcome"] == "blocked" and data["executed"] is False
    assert data["requested_domains"] == ["disk"]
    text = result["content"][0]["text"]
    assert "BLOCKED before running" in text and "Disk: /data (read-only), line 2; uses read" in text


def test_allowed_domain_runs_and_others_stay_blocked():
    server = mcp_server.Server(mcp_server.Policy(("disk",)))
    allowed = call(server, "koschei_run", source=READ_DATA)
    assert allowed["structuredContent"]["outcome"] == "ok"
    assert allowed["structuredContent"]["stdout"] == "missing\n"
    assert "Disk: /data (read-only)" in allowed["content"][0]["text"]
    blocked = call(server, "koschei_run", source=FETCH)
    assert blocked["structuredContent"]["outcome"] == "blocked"
    assert blocked["structuredContent"]["requested_domains"] == ["net"]


def test_check_never_executes():
    result = call(mcp_server.Server(mcp_server.Policy(("disk",))), "koschei_check", source=READ_DATA)
    assert result["structuredContent"]["executed"] is False
    assert result["structuredContent"]["outcome"] == "checked"
    assert "stdout" not in result["structuredContent"]


def test_compile_error_and_bad_arguments():
    server = mcp_server.Server()
    broken = call(server, "koschei_run", source="fn main( {")
    assert broken["isError"] and broken["structuredContent"]["outcome"] == "compile_error"
    assert "KS1003" in broken["content"][0]["text"]
    assert call(server, "koschei_run", source="")["isError"]
    assert call(server, "koschei_run", source="x" * (untrusted.MAX_SOURCE_BYTES + 1))["isError"]
    unknown = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert unknown["error"]["code"] == -32602
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})["error"]["code"] == -32601


def test_unknown_domain_is_rejected():
    with pytest.raises(ValueError):
        mcp_server.Policy(("root",))


def program(body: str) -> str:
    return "fn main(caps: SystemCaps) {\n" + body + "}\n"


def test_scoped_disk_policy():
    server = mcp_server.Server(mcp_server.Policy(read=("/data",), write=("/out/",)))
    inside = call(server, "koschei_run", source=READ_DATA)
    assert inside["structuredContent"]["outcome"] == "ok"
    for body, expected in [
        ('    let d = caps.disk.allow_read_only("/etc")\n    println(d.read("/etc/hostname") or "x")\n', "Disk read of /etc"),
        ('    let d = caps.disk.allow_read_only("/database")\n    println(d.read("/database/x") or "x")\n', "Disk read of /database"),
        ('    let d = caps.disk.allow_read_only("/data/../etc")\n    println(d.read("/etc/x") or "x")\n', "outside the allowed paths"),
        ('    let d = caps.disk.allow("/data")\n    println(d.read("/data/x") or "x")\n', "Disk write access to /data"),
    ]:
        result = call(server, "koschei_run", source=program(body))
        data = result["structuredContent"]
        assert data["outcome"] == "blocked" and data["executed"] is False, body
        assert expected in result["content"][0]["text"], result["content"][0]["text"]
    writable = call(server, "koschei_check", source=program('    let d = caps.disk.allow("/out/reports")\n    println(d.read("/out/reports/x") or "x")\n'))
    assert writable["structuredContent"]["outcome"] == "checked"
    readable = call(server, "koschei_check", source=program('    let d = caps.disk.allow_read_only("/out")\n    println(d.read("/out/x") or "x")\n'))
    assert readable["structuredContent"]["outcome"] == "checked"


def test_scoped_net_and_env_policy():
    server = mcp_server.Server(mcp_server.Policy(net=("https://api.example.com/",), env=("HOME",)))
    ok = call(server, "koschei_check", source=program('    let n = caps.net.allow("https://api.example.com")\n    println(n.get("https://api.example.com/v1") or "x")\n'))
    assert ok["structuredContent"]["outcome"] == "checked"
    other = call(server, "koschei_run", source=FETCH)
    assert other["structuredContent"]["outcome"] == "blocked"
    assert "Network access to https://collector.example.com" in other["content"][0]["text"]
    env_ok = call(server, "koschei_check", source=program('    println(caps.env.allow("HOME").get("HOME") or "x")\n'))
    assert env_ok["structuredContent"]["outcome"] == "checked"
    env_no = call(server, "koschei_run", source=program('    println(caps.env.allow("AWS_SECRET_ACCESS_KEY").get("AWS_SECRET_ACCESS_KEY") or "x")\n'))
    assert env_no["structuredContent"]["outcome"] == "blocked"
    disk = call(server, "koschei_run", source=READ_DATA)
    assert disk["structuredContent"]["outcome"] == "blocked"


def test_dynamic_scope_is_blocked_under_scoped_policy():
    source = (
        "fn pick() -> String {\n    return \"/data\"\n}\n\n"
        "fn main(caps: SystemCaps) {\n    let d = caps.disk.allow_read_only(pick())\n    println(d.read(\"/data/x\") or \"x\")\n}\n"
    )
    result = call(mcp_server.Server(mcp_server.Policy(read=("/data",))), "koschei_run", source=source)
    assert result["structuredContent"]["outcome"] == "blocked"
    assert "computed at run time" in result["content"][0]["text"]


def test_policy_description():
    policy = mcp_server.Policy(("env",), read=("/data",), write=("/out",), net=("https://api.example.com",))
    assert policy.describe() == (
        "disk read under /data; disk read and write under /out; network to https://api.example.com; env; clock; random"
    )
    assert mcp_server.Policy().describe() == "clock; random"


def test_quick_reference_programs_compile():
    """Every program in the reference the agent learns from must be valid."""
    programs = re.findall(r"```ks\n(.*?)```", mcp_server.QUICK_REFERENCE, re.DOTALL)
    assert len(programs) >= 2
    for source in programs:
        result = untrusted.evaluate(source, "check", "en", ())
        assert untrusted.outcome(result) == "checked", result["policy"]["stderr"]


def test_stdio_round_trip():
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "koschei_run", "arguments": {"source": HELLO}}},
    ]
    stdin = "".join(json.dumps(r) + "\n" for r in requests) + "not json\n"
    done = subprocess.run([sys.executable, "-m", "koschei.mcp_server"], input=stdin, capture_output=True, text=True, timeout=60)
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert [reply.get("id") for reply in replies] == [1, 2, None]
    assert replies[1]["result"]["structuredContent"]["stdout"] == "hello\n"
    assert replies[2]["error"]["code"] == -32700


def test_serve_ignores_blank_lines():
    out = io.StringIO()
    mcp_server.Server().serve(io.StringIO('\n{"jsonrpc":"2.0","id":7,"method":"ping"}\n'), out)
    assert json.loads(out.getvalue()) == {"jsonrpc": "2.0", "id": 7, "result": {}}
