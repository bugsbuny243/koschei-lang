"""Multi-request server (G4): Knowhere, Sakaar, POST and per-request budgets.

Each test runs a Koschei server under `ks run` in a subprocess and drives it
with real HTTP clients on loopback.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from koschei.cli_entry import main as cli_main
from koschei.modules import check_graph, load_graph
from koschei.semantic import SemanticError

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


SERVER = """
fn handle(server: ServeCaps, rounds: Int) -> Int {
    let mut served = 0
    let mut round = 0
    while round < rounds {
        round = round + 1
        let request = server.accept() or {
            println("accept error")
            continue
        }
        let name = request.header("X-Name") or "-"
        let body = request.body() or "<not text>"
        let raw = request.body_bytes()
        let text = "{request.method()} {request.path()} name={name} body={body} bytes={raw.length()}"
        let sent = server.reply(200, text) or {
            println("reply error")
            continue
        }
        served = served + 1
    }
    return served
}

fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:PORT", 6, 2048, 512, 3000)
    println("served {handle(server, ROUNDS)}")
}
"""


class ServeKnowhereTests(unittest.TestCase):
    def start(self, source: str) -> tuple[subprocess.Popen, int]:
        port = free_port()
        directory = tempfile.TemporaryDirectory(prefix="koschei-serve-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "server.ks"
        path.write_text(source.replace("PORT", str(port)), encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "koschei", "run", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
        )
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                return process, port
            except OSError:
                time.sleep(0.05)
        self.fail("server did not start listening")

    def finish(self, process: subprocess.Popen) -> str:
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, err.decode())
        return out.decode("utf-8")

    @staticmethod
    def http(port: int, method: str, path: str, body: bytes | None = None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")

    @staticmethod
    def raw(port: int, payload: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as client:
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while chunk := client.recv(4096):
                chunks.append(chunk)
        return b"".join(chunks)

    def test_requests_are_served_one_by_one_with_nothing_carried_over(self) -> None:
        process, port = self.start(SERVER.replace("ROUNDS", "5"))
        # The first probe connection of start() was accepted and closed: it is
        # round one and fails as a protocol error.
        self.assertEqual(
            self.http(port, "GET", "/items?id=7&q=a%20b", headers={"X-Name": "Ada"}),
            (200, "GET /items?id=7&q=a%20b name=Ada body= bytes=0"),
        )
        self.assertEqual(
            self.http(port, "POST", "/orders", body="çay".encode()),
            (200, "POST /orders name=- body=çay bytes=4"),
        )
        self.assertEqual(
            self.http(port, "POST", "/raw", body=b"\xff\xfe"),
            (200, "POST /raw name=- body=<not text> bytes=2"),
        )
        self.assertEqual(self.http(port, "GET", "/again"), (200, "GET /again name=- body= bytes=0"))
        self.assertEqual(self.finish(process), "accept error\nserved 4\n")

    def test_protocol_and_budget_failures_answer_and_keep_serving(self) -> None:
        process, port = self.start(SERVER.replace("ROUNDS", "5"))
        self.assertTrue(self.raw(port, b"GET / HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 400 "))
        status, _ = self.http(port, "POST", "/big", body=b"x" * 4096)
        self.assertEqual(status, 413)
        self.assertTrue(
            self.raw(port, b"POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
            .startswith(b"HTTP/1.1 400 ")
        )
        self.assertEqual(self.http(port, "GET", "/ok"), (200, "GET /ok name=- body= bytes=0"))
        self.assertEqual(self.finish(process), "accept error\n" * 4 + "served 1\n")

    def test_an_unanswered_request_is_closed_not_carried(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:PORT", 4, 2048, 512, 3000)
    let probe = server.accept()
    let first = server.accept() or Error("skip")
    println(server.accept())
    let second = server.accept() or {
        println("no second")
        return
    }
    println(second.path())
    println(server.reply(200, "fresh") or Error("x"))
    println(server.reply(200, "twice"))
}
"""
        process, port = self.start(source)
        # probe = the start() connection (an error); first = /one, then the
        # next accept() finds /one unanswered: it gets 500 and KS3470.
        status_one, _ = self.http(port, "GET", "/one")
        self.assertEqual(status_one, 500)
        self.assertEqual(self.http(port, "GET", "/two"), (200, "fresh"))
        self.assertEqual(
            self.finish(process),
            "KS3470: Önceki istek yanıtlanmadan yeni istek kabul edilemez; önceki istek 500 ile kapatıldı.\n"
            "/two\nunit\nKS3470: Yanıtlanacak bekleyen bir istek yok.\n",
        )

    def test_reply_rules_and_the_request_budget(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:PORT", 4, 2048, 120, 3000)
    let probe = server.accept()
    let a = server.accept() or Error("a")
    println(server.reply(299, "odd"))
    let b = server.accept() or Error("b")
    println(server.reply(200, "this response is far too long for a one hundred and twenty byte budget, by design"))
    let c = server.accept() or Error("c")
    println(server.reply(204, "") or Error("x"))
    println(server.accept())
}
"""
        process, port = self.start(source)
        self.assertEqual(self.http(port, "GET", "/a")[0], 500)
        self.assertEqual(self.http(port, "GET", "/b")[0], 500)
        self.assertEqual(self.http(port, "GET", "/c"), (204, ""))
        self.assertEqual(
            self.finish(process),
            "KS3472: Desteklenmeyen HTTP durum kodu: 299.\n"
            "KS3410: response exceeds max_response_bytes\n"
            "unit\n"
            "KS3471: Sunucunun istek bütçesi tükendi: en fazla 4 istek kabul edilebilir.\n",
        )

    def test_accept_waits_at_most_the_deadline(self) -> None:
        source = """
fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:PORT", 4, 2048, 512, 300)
    let probe = server.accept()
    println(server.accept())
}
"""
        process, _ = self.start(source)
        self.assertEqual(self.finish(process), "KS3411: accept exceeded the I/O deadline\n")

    def check_error(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            graph = load_graph(path)
            with self.assertRaises(SemanticError) as caught:
                check_graph(graph)
        return caught.exception.code

    def test_the_checker_and_the_native_gate(self) -> None:
        head = 'fn main(caps: SystemCaps) {\n    let s = caps.serve.allow("127.0.0.1:9", 1, 64, 64, 10)\n'
        self.assertEqual(self.check_error(head + '    let x = s.reply("200", "a")\n}\n'), "KS1301")
        self.assertEqual(self.check_error(head + "    let x = s.accept(1)\n}\n"), "KS1301")
        for call in (
            's.reply_as(200, "a")', 's.reply_as("200", "text/html", "a")', 's.reply_as(200, 5, "a")',
            's.reply_as(200, "text/html", 5)', 's.reply_with(200, "text/html", "a")',
            's.reply_with(200, "text/html", [1], "a")', 's.reply_with(200, "text/html", ["A: b"])',
        ):
            with self.subTest(call):
                self.assertEqual(self.check_error(head + f"    let x = {call}\n}}\n"), "KS1301")
        self.assertEqual(
            self.check_error(head + "    let r = s.accept() or return\n    let q = r.query()\n}\n"),
            "KS1306",
        )
        for call in ("r.cookie()", "r.cookie(1)"):
            with self.subTest(call):
                self.assertEqual(
                    self.check_error(head + f"    let r = s.accept() or return\n    let q = {call}\n}}\n"),
                    "KS1301",
                )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            # accept/reply compile through the broker (tests/test_native_serve_v1.py);
            # the one-shot exchange does not.
            path.write_text(head + '    let body = s.exchange("hi") or return\n    println(body)\n}\n', encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli_main(["build", str(path), "-o", str(Path(directory) / "bin")]), 1)
            self.assertIn("KS4004", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
