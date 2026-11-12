"""ServeCaps.reply_with: redirects, cookies and the program's own response headers.

The same server runs under `ks run` and as a native binary; every client reads
the same bytes from both, and both print the same Error values.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from koschei.cli_entry import main as cli_main
from koschei.serve_knowhere_v1 import HEADERS_MESSAGE, response_headers, CONTENT_TYPE_MESSAGE

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

# One path per case. Each reply's Error, if any, is printed.
CASES = [
    ("/redirect", '303, {"Location": "/done?x=1", "Set-Cookie": "sid=abc123; HttpOnly; Secure; Path=/; SameSite=Lax"}, ""'),
    ("/moved", '301, {"Location": "https://example.com/"}, ""'),
    ("/found", '302, {"Location": "/a"}, ""'),
    ("/temporary", '307, {"Location": "/b"}, ""'),
    ("/permanent", '308, {"Location": "/c"}, ""'),
    ("/login", '401, {"WWW-Authenticate": "Basic realm=\\"koschei\\""}, "who are you?"'),
    ("/html", '200, {"content-type": "text/html; charset=utf-8", "X-Frame-Options": "DENY", "Cache-Control": "no-store"}, "<b>hi</b>"'),
    ("/empty", "200, empty, \"plain\""),
    ("/cookie", '200, {"Content-Type": "application/json"}, cookie_json(request)'),
    ("/length", '200, {"Content-Length": "1"}, "x"'),
    ("/chunked", '200, {"transfer-encoding": "chunked"}, "x"'),
    ("/connection", '200, {"Connection": "keep-alive"}, "x"'),
    ("/twice", '200, {"X-A": "1", "x-a": "2"}, "x"'),
    ("/name", '200, {"Bad Name": "1"}, "x"'),
    ("/inject", '200, {"X-A": "1\\r\\nX-Evil: yes"}, "x"'),
    ("/space", '200, {"X-A": " padded"}, "x"'),
    ("/unicode", '200, {"X-A": "çay"}, "x"'),
    ("/blank", '200, {"X-A": ""}, "x"'),
    ("/type", '200, {"Content-Type": "text/html\\r\\nX-Evil: yes"}, "x"'),
    ("/many", "200, many(), \"x\""),
    ("/status", '302, {"Location": "/"}, ""'),
]


def program(bind: str) -> str:
    branches = []
    for path, arguments in CASES:
        branches.append(
            f'''        if path == "{path}" {{
            let sent = server.reply_with({arguments})
            println("{path} {{sent}}")
        }}'''
        )
    body = "\n".join(branches)
    return f"""import http
import json

fn many() -> Map<String, String> {{
    let mut headers: Map<String, String> = {{}}
    let mut index = 0
    while index < 33 {{
        headers = headers.set("X-H{{index}}", "v")
        index = index + 1
    }}
    return headers
}}

fn cookie_json(request: HttpRequest) -> String {{
    let header = request.header("Cookie") or ""
    let found = http.cookies(header)
    let mut members: Map<String, String> = {{}}
    for key in found.keys() {{
        let value = found.get(key) or ""
        members = members.set(key, json.string(value))
    }}
    return json.object(members)
}}

fn serve(server: ServeCaps, rounds: Int) -> Int {{
    let empty: Map<String, String> = {{}}
    let mut round = 0
    while round < rounds {{
        round = round + 1
        let request = server.accept() or {{
            continue
        }}
        let path = request.path()
{body}
    }}
    return round
}}

fn main(caps: SystemCaps) {{
    let server = caps.serve.allow("{bind}", {len(CASES)}, 4096, 8192, 5000)
    println(serve(server, {len(CASES)}))
}}
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def raw_get(port: int, path: str, extra: str = "") -> bytes:
    deadline = time.monotonic() + 30
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=10) as client:
                client.sendall(f"GET {path} HTTP/1.1\r\nHost: t\r\n{extra}\r\n".encode("ascii"))
                chunks = []
                while chunk := client.recv(4096):
                    chunks.append(chunk)
                return b"".join(chunks)
        except ConnectionRefusedError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


class ResponseHeaderRuleTests(unittest.TestCase):
    def test_rules(self) -> None:
        self.assertEqual(response_headers([]), ("text/plain; charset=utf-8", []))
        self.assertEqual(
            response_headers([("Location", "/x"), ("CONTENT-TYPE", "text/html")]),
            ("text/html", [("Location", "/x")]),
        )
        self.assertEqual(response_headers([("Content-Type", "")]), CONTENT_TYPE_MESSAGE)
        for pairs in (
            [("X", "a\nb")], [("X", "a\tb")], [("X", "a ")], [("X", "")], [("X", "é")],
            [("X:", "a")], [("", "a")], [("x" * 65, "a")], [("X", "a" * 4097)],
            [("Te", "x")], [("Upgrade", "h2c")], [("Proxy-Connection", "x")], [("Trailer", "x")],
            [("Keep-Alive", "x")], [("X", "1"), ("x", "2")], [(f"X{index}", "v") for index in range(33)],
        ):
            self.assertEqual(response_headers(pairs), HEADERS_MESSAGE, pairs)
        self.assertEqual(len(response_headers([(f"X{index}", "v") for index in range(32)])[1]), 32)
        self.assertEqual(response_headers([("X", "a" * 4096)])[1], [("X", "a" * 4096)])


class ReplyWithServerTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="koschei-reply-with-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "server.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def drive(self, command: list[str], port: int) -> tuple[dict[str, bytes], str]:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
        )
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        replies = {}
        for path, _ in CASES:
            extra = "Cookie: sid=abc; theme=dark; sid=old\r\n" if path == "/cookie" else ""
            replies[path] = raw_get(port, path, extra)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, err.decode())
        return replies, out.decode("utf-8")

    def run_server(self) -> tuple[Path, dict[str, bytes], str]:
        port = free_port()
        path = self.write(program(f"127.0.0.1:{port}"))
        replies, output = self.drive([sys.executable, "-m", "koschei", "run", str(path)], port)
        return path, replies, output

    def check_replies(self, replies: dict[str, bytes], output: str) -> None:
        self.assertEqual(
            replies["/redirect"],
            b"HTTP/1.1 303 See Other\r\nContent-Type: text/plain; charset=utf-8\r\n"
            b"Location: /done?x=1\r\nSet-Cookie: sid=abc123; HttpOnly; Secure; Path=/; SameSite=Lax\r\n"
            b"Content-Length: 0\r\nConnection: close\r\n\r\n",
        )
        for path, line in (
            ("/moved", b"HTTP/1.1 301 Moved Permanently\r\n"), ("/found", b"HTTP/1.1 302 Found\r\n"),
            ("/temporary", b"HTTP/1.1 307 Temporary Redirect\r\n"),
            ("/permanent", b"HTTP/1.1 308 Permanent Redirect\r\n"), ("/login", b"HTTP/1.1 401 Unauthorized\r\n"),
        ):
            self.assertTrue(replies[path].startswith(line), path)
        self.assertIn(b'WWW-Authenticate: Basic realm="koschei"\r\n', replies["/login"])
        self.assertEqual(
            replies["/html"],
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nX-Frame-Options: DENY\r\n"
            b"Cache-Control: no-store\r\nContent-Length: 9\r\nConnection: close\r\n\r\n<b>hi</b>",
        )
        self.assertTrue(replies["/empty"].endswith(b"Content-Type: text/plain; charset=utf-8\r\nContent-Length: 5\r\nConnection: close\r\n\r\nplain"))
        self.assertTrue(replies["/cookie"].endswith(b'\r\n\r\n{"sid":"abc","theme":"dark"}'))
        refused = ["/length", "/chunked", "/connection", "/twice", "/name", "/inject", "/space", "/unicode", "/blank", "/type", "/many"]
        for path in refused:
            self.assertTrue(replies[path].startswith(b"HTTP/1.1 500 Internal Server Error\r\n"), path)
            self.assertNotIn(b"Evil", replies[path])
        lines = output.splitlines()
        expected = []
        for path, _ in CASES:
            if path in refused:
                expected.append(f"{path} {CONTENT_TYPE_MESSAGE if path == '/type' else HEADERS_MESSAGE}")
            else:
                expected.append(f"{path} unit")
        expected.append(str(len(CASES)))
        self.assertEqual(lines, expected)

    def test_ks_run(self) -> None:
        _, replies, output = self.run_server()
        self.check_replies(replies, output)

    @unittest.skipIf(GO is None, "Go is not installed")
    def test_native_binary_sends_the_same_bytes(self) -> None:
        path, expected_replies, expected_output = self.run_server()
        port = free_port()
        source = program(f"127.0.0.1:{port}")
        native_path = self.write(source)
        binary = native_path.parent / "server"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(native_path), "-o", str(binary)]), 0, errors.getvalue())
        replies, output = self.drive([str(binary)], port)
        self.assertEqual(replies, expected_replies)
        self.assertEqual(output, expected_output)

    def test_checker_requires_a_string_map(self) -> None:
        source = """fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:9", 1, 100, 100, 100)
    let headers = {"a": 1}
    let sent = server.reply_with(200, headers, "x")
}
"""
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stdout):
            code = cli_main(["check", str(self.write(source))])
        self.assertEqual(code, 1)
        self.assertIn("KS1301", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
