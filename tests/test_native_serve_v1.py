"""The multi-request loopback server in native binaries (G4 through the G2 broker).

The same Koschei server runs under `ks run` and as a binary; the same clients
send the same bytes, and the replies they read and the program's output must
be identical. The listener lives in the broker; the worker has no sockets.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from koschei import serve_knowhere_v1 as _serve

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")
SUPPORTED = GO is not None and sys.platform == "linux" and platform.machine() in {"x86_64", "AMD64"}

SERVER = """
fn handle(server: ServeCaps) -> Int {
    let mut served = 0
    while served < ROUNDS {
        served = served + 1
        let attempt = server.accept()
        println(attempt)
        let request = attempt or {
            continue
        }
        println(request.header("X-Name"))
        println(request.header("x-NAME"))
        println(request.header("Missing"))
        println(request.body())
        println(request.body_bytes())
        let path = request.path()
        if path == "/teapot" {
            println(server.reply(418, "x"))
            continue
        }
        if path == "/empty" {
            println(server.reply(204, "x"))
            continue
        }
        if path == "/nothing" {
            println(server.reply(204, ""))
            continue
        }
        if path == "/big" {
            println(server.reply(200, "{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}{path}"))
            continue
        }
        if path == "/bytes" {
            println(server.reply(201, request.body_bytes()))
            continue
        }
        if path == "/twice" {
            println(server.accept())
            continue
        }
        if path == "/json" {
            println(server.reply_as(200, "application/json", "\\{\\"ok\\": true\\}"))
            continue
        }
        if path == "/html" {
            println(server.reply_as(201, "text/html; charset=utf-8", request.body_bytes()))
            continue
        }
        if path == "/inject" {
            println(server.reply_as(200, "text/html\\r\\nX-Injected: 1", "x"))
            continue
        }
        if path == "/spaced" {
            println(server.reply_as(200, " text/html", "x"))
            continue
        }
        println(server.reply(200, "{request.method()} {path} merhaba"))
    }
    println(server.reply(200, "late"))
    println(server.accept())
    return served
}

fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:PORT", CONNECTIONS, 300, 120, 4000)
    println(handle(server))
}
"""

# A fresh server on the same bind each round: a dropped server closes its
# listener and its unanswered connection, so the next one can listen. A server
# lives as long as a MIR slot holds it, in both executors: each round's slots
# are overwritten before the next accept(), and the last server of the 10 ms
# rounds is still held when `held` asks for the same bind.
ROUNDS_PROGRAM = """
fn main(caps: SystemCaps) {
    let mut index = 0
    while index < 6 {
        index = index + 1
        let server = caps.serve.allow("127.0.0.1:PORT", 4, 4096, 4096, 4000)
        println(server.accept())
    }
    while index < 40 {
        index = index + 1
        let server = caps.serve.allow("127.0.0.1:SECOND", 4, 4096, 4096, 10)
        println(server.accept())
    }
    let held = caps.serve.allow("127.0.0.1:SECOND", 1, 4096, 4096, 10)
    println(held.accept())
}
"""

HOST = b"Host: a\r\n"
REQUESTS: list[tuple[bytes, float]] = [
    (b"GET /ok?a=%41 HTTP/1.1\r\nHost: x\r\nX-Name: Ada\r\n\r\n", 0),
    (b"GET /h HTTP/1.1\r\nHost: \r\n\r\n", 0),
    (b"GET /h HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n", 0),
    (b"GET /h#f HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /h HTTP/1.1\r\n" + HOST + b"X: a\x01b\r\n\r\n", 0),
    (b"GET /h HTTP/1.1\r\n" + HOST + b"Content-Length: +1\r\n\r\nx", 0),
    (b"GET /h HTTP/1.1\r\n" + HOST + b"Content-Length: 1\r\n\r\nxy", 0),
    (b"G1T /h HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"POST /bytes HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\n\r\n\xff\x00a", 0),
    (b"POST /p HTTP/1.0\r\nContent-Length: 5\r\nX-Name:  caf\xe9 \t\r\n\r\nh\xc3\xa9yy", 0),
    (b"get /low HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /x HTTP/2.0\r\n\r\n", 0),
    (b"GET /x HTTP/1.1\r\nBad Name: v\r\n\r\n", 0),
    (b"GET /x HTTP/1.1\r\n" + HOST + b"Transfer-Encoding: chunked\r\n\r\n", 0),
    (b"GET /x HTTP/1.1\r\n" + HOST + b"Content-Length: 1\r\nContent-Length: 1\r\n\r\nx", 0),
    (b"POST /x HTTP/1.1\r\n" + HOST + b"Content-Length: 999\r\n\r\n", 0),
    (b"GET /" + b"a" * 400 + b" HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    # Past the 4 s deadline with room to spare; the deadline itself leaves a
    # slow (CI) machine time to serve every other request under ks run.
    (b"GET /slow HTTP/1.1\r\n", 6.0),
    (b"POST /cut HTTP/1.1\r\n" + HOST + b"Content-Length: 9\r\n\r\nabc", -1),
    (b"GET /teapot HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /empty HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /nothing HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /big HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /twice HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /json HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"POST /html HTTP/1.1\r\n" + HOST + b"Content-Length: 4\r\n\r\n<b>!", 0),
    (b"GET /inject HTTP/1.1\r\n" + HOST + b"\r\n", 0),
    (b"GET /spaced HTTP/1.1\r\n" + HOST + b"\r\n", 0),
]


def worker_pids(broker: int) -> list[int]:
    """Children of every thread of the broker: Go may start the worker from
    any OS thread, and /proc lists children per thread."""

    pids: list[int] = []
    for task in Path(f"/proc/{broker}/task").glob("*"):
        try:
            pids += [int(item) for item in (task / "children").read_text().split()]
        except OSError:
            continue
    return pids


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _exchange(port: int, raw: bytes, pause: float) -> bytes:
    for _ in range(200):
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=10)
            break
        except OSError:
            time.sleep(0.05)
    else:
        raise AssertionError("server did not start")
    with client:
        client.sendall(raw)
        if pause < 0:
            # The client gives up half way through its body.
            client.shutdown(socket.SHUT_WR)
        elif pause:
            time.sleep(pause)
        data = b""
        try:
            while chunk := client.recv(65536):
                data += chunk
        except OSError as error:
            data += f"<{type(error).__name__}>".encode()
    return data


@unittest.skipUnless(SUPPORTED, "the broker is linux/amd64")
class NativeServeParityTests(unittest.TestCase):
    def serve(self, command: list[str], cwd: Path, port: int, requests: list[tuple[bytes, float]]) -> tuple[list[bytes], bytes, int]:
        process = subprocess.Popen(
            command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
        )
        try:
            replies = [_exchange(port, raw, pause) for raw, pause in requests]
            stdout, stderr = process.communicate(timeout=120)
        finally:
            process.kill()
        self.assertEqual(stderr, b"")
        return replies, stdout, process.returncode

    def both(self, source: str, port: int, requests: list[tuple[bytes, float]]) -> tuple[list[bytes], str]:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            build = subprocess.run(
                [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], cwd=base,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, timeout=300, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr.decode())
            interpreted = self.serve([sys.executable, "-m", "koschei", "run", "main.ks"], base, port, requests)
            native = self.serve([str(base / "app")], base, port, requests)
        self.assertEqual(native[0], interpreted[0])
        self.assertEqual(native[1], interpreted[1])
        self.assertEqual(native[2], interpreted[2])
        return interpreted[0], interpreted[1].decode()

    def test_requests_match_ks_run(self) -> None:
        port = free_port()
        source = (
            SERVER.replace("PORT", str(port))
            .replace("CONNECTIONS", "100")
            .replace("ROUNDS", str(len(REQUESTS) + 1))
        )
        replies, output = self.both(source, port, REQUESTS)
        self.assertTrue(replies[0].endswith(b"\r\n\r\nGET /ok?a=%41 merhaba"))
        self.assertIn(b"Connection: close\r\n", replies[0])
        self.assertTrue(replies[8].startswith(b"HTTP/1.1 201 Created\r\n"))
        self.assertTrue(replies[8].endswith(b"\xff\x00a"))
        for index in (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17, 18):
            self.assertTrue(replies[index].startswith(b"HTTP/1.1 400 Bad Request\r\n"), index)
        for index in (15, 16):
            self.assertTrue(replies[index].startswith(b"HTTP/1.1 413 Content Too Large\r\n"), index)
        for index in (19, 20, 22, 23):
            self.assertTrue(replies[index].startswith(b"HTTP/1.1 500 Internal Server Error\r\n"), index)
        self.assertTrue(replies[21].startswith(b"HTTP/1.1 204 No Content\r\n"))
        self.assertEqual(replies[24], (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 12\r\n"
            b'Connection: close\r\n\r\n{"ok": true}'
        ))
        self.assertEqual(replies[25], (
            b"HTTP/1.1 201 Created\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: 4\r\n"
            b"Connection: close\r\n\r\n<b>!"
        ))
        # A content type that could add a header is never sent: the client
        # gets 500 and reply_as() the Error value.
        for index in (26, 27):
            self.assertTrue(replies[index].startswith(b"HTTP/1.1 500 Internal Server Error\r\n"), index)
            self.assertNotIn(b"X-Injected", replies[index])
        self.assertEqual(output.count(_serve.CONTENT_TYPE_MESSAGE + "\n"), 2)
        for expected in (
            "KS3410: Host header may not be empty",
            "KS3410: exchange v1 accepts uppercase alphabetic HTTP methods only",
            "KS3410: HTTP header value contains a control byte",
            "café",
            "KS3430: İstek gövdesi geçerli UTF-8 metin değil.",
            "Bytes(ff0061)",
            "KS3411: request read exceeded the I/O deadline",
            "KS3410: connection closed before request body completed",
            "KS3472: Desteklenmeyen HTTP durum kodu: 418.",
            "KS3472: 204 yanıtı gövde taşıyamaz.",
            "KS3410: response exceeds max_response_bytes",
            "KS3470: Önceki istek yanıtlanmadan yeni istek kabul edilemez; önceki istek 500 ile kapatıldı.",
            "KS3411: accept exceeded the I/O deadline",
            "KS3470: Yanıtlanacak bekleyen bir istek yok.",
        ):
            self.assertIn(expected + "\n", output)

    def test_budget_and_listener_failures_match_ks_run(self) -> None:
        port = free_port()
        source = SERVER.replace("PORT", str(port)).replace("CONNECTIONS", "2").replace("ROUNDS", "3")
        ok = (b"GET /ok HTTP/1.1\r\n" + HOST + b"\r\n", 0.0)
        _replies, output = self.both(source, port, [ok, ok])
        self.assertIn("KS3471: Sunucunun istek bütçesi tükendi: en fazla 2 istek kabul edilebilir.\n", output)
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen(1)
            taken = holder.getsockname()[1]
            source = SERVER.replace("PORT", str(taken)).replace("CONNECTIONS", "1").replace("ROUNDS", "1")
            _replies, output = self.both(source, taken, [])
        self.assertTrue(output.startswith("KS3411: listener failed: EADDRINUSE\n"), output)

    def test_dropped_servers_release_their_bind(self) -> None:
        port, second = free_port(), free_port()
        source = ROUNDS_PROGRAM.replace("SECOND", str(second)).replace("PORT", str(port))
        requests = [(f"GET /{index} HTTP/1.1\r\n".encode() + HOST + b"\r\n", 0.0) for index in range(6)]
        replies, output = self.both(source, port, requests)
        # Unanswered: each connection closed with its server.
        self.assertEqual(replies, [b""] * 6)
        self.assertEqual(
            output,
            "".join(f"HttpRequest(GET /{index})\n" for index in range(6))
            + "KS3411: accept exceeded the I/O deadline\n" * 34
            + "KS3411: listener failed: EADDRINUSE\n",
        )

    def test_the_worker_holds_no_listener(self) -> None:
        port = free_port()
        source = SERVER.replace("PORT", str(port)).replace("CONNECTIONS", "1").replace("ROUNDS", "1")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            subprocess.run(
                [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], cwd=base,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, timeout=300, check=True,
            )
            process = subprocess.Popen([str(base / "app")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                client = None
                for _ in range(200):
                    try:
                        client = socket.create_connection(("127.0.0.1", port), timeout=5)
                        break
                    except OSError:
                        time.sleep(0.05)
                self.assertIsNotNone(client)
                children = worker_pids(process.pid)
                self.assertEqual(len(children), 1)
                worker = children[0]
                status = Path(f"/proc/{worker}/status").read_text()
                self.assertIn("Seccomp:\t2", status)
                sockets = [
                    os.readlink(f"/proc/{worker}/fd/{fd}") for fd in os.listdir(f"/proc/{worker}/fd")
                ]
                # Only the broker channel: descriptor 3.
                self.assertEqual(sum(1 for target in sockets if target.startswith("socket:")), 1)
                client.sendall(b"GET /ok HTTP/1.1\r\n" + HOST + b"\r\n")
                client.recv(4096)
                client.close()
                process.communicate(timeout=60)
            finally:
                process.kill()


if __name__ == "__main__":
    unittest.main()
