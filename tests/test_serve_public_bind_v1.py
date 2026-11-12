"""Public Serve binds: `0.0.0.0:PORT` and `[::]:PORT`, and nothing else beyond loopback."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import http.client
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
from koschei.serve_public_bind_v1 import parse_public_bind

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

# Serves ROUNDS requests per server, then opens a fresh server on the same
# bind: max_connections bounds one token, not the life of the program.
SERVER = """import http
import json

fn respond(target: String) -> String {
    let found = http.route("/users/:name", target) or return "no route"
    let name = found.get("name") or "?"
    return json.object({"name": json.string(name)})
}

fn serve(server: ServeCaps, rounds: Int) -> Int {
    let mut served = 0
    let mut round = 0
    while round < rounds {
        round = round + 1
        let request = server.accept() or {
            continue
        }
        let sent = server.reply_as(200, "application/json", respond(request.path())) or {
            continue
        }
        served = served + 1
    }
    return served
}

fn main(caps: SystemCaps) {
    let mut total = 0
    let mut servers = 0
    while servers < 2 {
        servers = servers + 1
        let server = caps.serve.allow("BIND", 3, 4096, 4096, 5000)
        total = total + serve(server, 3)
    }
    println("served {total}")
}
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def outside_address() -> str:
    """This machine's address on its default route, or loopback when it has none."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"
    return address if address != "0.0.0.0" else "127.0.0.1"


class PublicBindRuleTests(unittest.TestCase):
    def test_exact_spellings_only(self) -> None:
        self.assertEqual(parse_public_bind("0.0.0.0:8080"), ("0.0.0.0", 8080))
        self.assertEqual(parse_public_bind("[::]:443"), ("::", 443))
        self.assertEqual(parse_public_bind(" 0.0.0.0:1 "), ("0.0.0.0", 1))
        for refused in (
            "0.0.0.0:0", "0.0.0.0:65536", "0.0.0.0:", "0.0.0.0", "0.0.0.00:80",
            "[0.0.0.0]:80", "::8080", ":::8080", "[::]8080", "[::0]:80", "10.0.0.1:80",
            "0.0.0.0:80x", "0.0.0.0:+80", "０.0.0.0:80", "0.0.0.0:８０",
        ):
            self.assertIsNone(parse_public_bind(refused), refused)


class PublicBindProgramTests(unittest.TestCase):
    def write(self, source: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="koschei-public-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "server.ks"
        path.write_text(source, encoding="utf-8")
        return path

    def cli(self, *arguments: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stdout):
            code = cli_main(list(arguments))
        return code, stdout.getvalue()

    def test_checker_and_manifest(self) -> None:
        for bind in ("0.0.0.0:8080", "[::]:8080"):
            path = self.write(SERVER.replace("BIND", bind))
            code, output = self.cli("check", str(path))
            self.assertEqual(code, 0, output)
            code, output = self.cli("caps", str(path))
            self.assertEqual(code, 0, output)
            self.assertIn(f"{bind} | connections=3", output)
            code, output = self.cli("caps", "--deny", "serve", str(path))
            self.assertEqual(code, 2, output)
        for bind in ("10.0.0.1:8080", "0.0.0.0:0", "[0.0.0.0]:8080", "[::0]:8080", "0.0.0.00:80"):
            code, output = self.cli("check", str(self.write(SERVER.replace("BIND", bind))))
            self.assertEqual(code, 1, bind)
            self.assertIn("KS2411", output, bind)

    def drive(self, command: list[str], port: int) -> str:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
        )
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        host = outside_address()
        replies = []
        for index in range(6):
            deadline = time.monotonic() + 30
            while True:
                try:
                    connection = http.client.HTTPConnection(host, port, timeout=10)
                    connection.request("GET", f"/users/u{index}")
                    response = connection.getresponse()
                    replies.append((response.status, response.read().decode("utf-8")))
                    break
                except (ConnectionRefusedError, ConnectionResetError, http.client.RemoteDisconnected):
                    if time.monotonic() > deadline:
                        self.fail(f"request {index} was never answered")
                    time.sleep(0.05)
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, err.decode())
        self.assertEqual(replies, [(200, f'{{"name":"u{index}"}}') for index in range(6)])
        return out.decode("utf-8")

    def test_ks_run_serves_every_interface(self) -> None:
        port = free_port()
        path = self.write(SERVER.replace("BIND", f"0.0.0.0:{port}"))
        output = self.drive([sys.executable, "-m", "koschei", "run", str(path)], port)
        self.assertEqual(output, "served 6\n")

    @unittest.skipIf(GO is None, "Go is not installed")
    def test_native_binary_serves_every_interface(self) -> None:
        port = free_port()
        path = self.write(SERVER.replace("BIND", f"0.0.0.0:{port}"))
        binary = path.parent / "server"
        code, output = self.cli("build", str(path), "-o", str(binary))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.drive([str(binary)], port), "served 6\n")


if __name__ == "__main__":
    unittest.main()
