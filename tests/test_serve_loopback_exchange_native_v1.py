from __future__ import annotations

import pathlib
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from koschei.codegen_go import CodegenError, generate_go
from koschei.parser import parse
from koschei.semantic import check


GO_BINARY = shutil.which("go")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _source(port: int, *, response: str = "accepted", deadline_ms: int = 2000, response_bytes: int = 4096) -> str:
    return (
        "fn main(caps: SystemCaps) {\n"
        f'let server = caps.serve.allow("localhost:{port}", 8, 4096, {response_bytes}, {deadline_ms})\n'
        f'let body = server.exchange("{response}") or return\n'
        "println(body)\n"
        "}"
    )


def _connect_when_ready(port: int, process: subprocess.Popen[str]) -> socket.socket:
    deadline = time.monotonic() + 3.0
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.2)
        except OSError as error:
            last_error = error
            time.sleep(0.01)
    stdout, stderr = process.communicate(timeout=1)
    raise AssertionError(
        f"native Serve listener did not become ready: {last_error}; "
        f"returncode={process.returncode}; stdout={stdout!r}; stderr={stderr!r}"
    )


class ServeLoopbackExchangeNativeShapeTests(unittest.TestCase):
    def test_linux_codegen_contains_backlog_bound_serve_runtime(self) -> None:
        port = _free_loopback_port()
        program = parse(_source(port))
        check(program)
        with patch("koschei.serve_loopback_exchange_go_v1.sys.platform", "linux"):
            generated = generate_go(program)

        self.assertIn('"net"', generated)
        self.assertIn('"unicode/utf8"', generated)
        self.assertIn("type ksServeCaps struct", generated)
        self.assertIn("syscall.Listen(fd, int(policy.maxConnections))", generated)
        self.assertIn("func ksServeExchange(", generated)
        self.assertIn("case *ksServeCaps:", generated)
        self.assertNotIn(
            'if n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı")\n',
            generated,
        )

    def test_non_linux_native_serve_remains_fail_closed(self) -> None:
        port = _free_loopback_port()
        program = parse(_source(port))
        check(program)
        with patch("koschei.serve_loopback_exchange_go_v1.sys.platform", "darwin"):
            with self.assertRaisesRegex(CodegenError, "KS4001"):
                generate_go(program)


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native Serve testleri atlandı")
@unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native Serve v1 Linux-only")
class ServeLoopbackExchangeNativeRuntimeTests(unittest.TestCase):
    def build(self, source: str) -> pathlib.Path:
        program = parse(source)
        check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-serve-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheiserve\n\ngo 1.21\n",
            encoding="utf-8",
        )
        binary = directory / "program"
        completed = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return binary

    def start(self, source: str) -> tuple[subprocess.Popen[str], int]:
        port = int(source.split('localhost:', 1)[1].split('"', 1)[0])
        binary = self.build(source)
        process = subprocess.Popen(
            [str(binary)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process, port

    def test_real_native_post_matches_interpreter_wire_contract(self) -> None:
        port = _free_loopback_port()
        process, _ = self.start(_source(port))
        body = b'{"b":2,"a":1}'
        request = (
            b"POST /orders HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"\r\n"
            + body
        )

        with _connect_when_ready(port, process) as client:
            client.settimeout(2.0)
            client.sendall(request)
            response = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        stdout, stderr = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(stdout, '{"b":2,"a":1}\n')
        self.assertEqual(stderr, "")
        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertTrue(response.endswith(b"\r\n\r\naccepted"), response)

    def test_native_transfer_encoding_is_rejected(self) -> None:
        port = _free_loopback_port()
        process, _ = self.start(_source(port))
        with _connect_when_ready(port, process) as client:
            client.sendall(
                b"POST / HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
                b"0\r\n\r\n"
            )

        stdout, stderr = process.communicate(timeout=3)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(stdout, "")
        self.assertIn("KS3410", stderr)
        self.assertIn("Transfer-Encoding", stderr)

    def test_native_duplicate_content_length_is_rejected(self) -> None:
        port = _free_loopback_port()
        process, _ = self.start(_source(port))
        with _connect_when_ready(port, process) as client:
            client.sendall(
                b"POST / HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Content-Length: 1\r\n"
                b"Content-Length: 1\r\n\r\n"
                b"x"
            )

        stdout, stderr = process.communicate(timeout=3)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(stdout, "")
        self.assertIn("KS3410", stderr)
        self.assertIn("Content-Length", stderr)

    def test_native_response_budget_fails_before_listener_wait(self) -> None:
        port = _free_loopback_port()
        binary = self.build(_source(port, response="accepted", deadline_ms=2000, response_bytes=32))
        started = time.monotonic()
        completed = subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        elapsed = time.monotonic() - started
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("KS3410", completed.stderr)
        self.assertIn("max_response_bytes", completed.stderr)
        self.assertLess(elapsed, 2.0)

    def test_native_accept_is_bounded_by_absolute_io_deadline(self) -> None:
        port = _free_loopback_port()
        binary = self.build(_source(port, deadline_ms=150))
        started = time.monotonic()
        completed = subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        elapsed = time.monotonic() - started
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("KS3411", completed.stderr)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
