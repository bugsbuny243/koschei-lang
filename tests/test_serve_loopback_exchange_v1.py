from __future__ import annotations

import io
import socket
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze
from koschei.diagnostics import CATALOG, ENGLISH_CATALOG
from koschei.interpreter import run
from koschei.parser import parse
from koschei.semantic import check


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run_capture(source: str) -> tuple[int, str, str]:
    output = io.StringIO()
    error = io.StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = run(parse(source), [])
    return code, output.getvalue(), error.getvalue()


def _connect_when_ready(port: int, thread: threading.Thread) -> socket.socket:
    deadline = time.monotonic() + 2.5
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if not thread.is_alive():
            break
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.2)
        except OSError as error:
            last_error = error
            time.sleep(0.01)
    raise AssertionError(f"listener did not become ready: {last_error}")


class ServeLoopbackExchangeV1Tests(unittest.TestCase):
    def test_real_post_body_crosses_bounded_loopback_exchange(self) -> None:
        port = _free_loopback_port()
        source = (
            "fn main(caps: SystemCaps) { "
            f'let server = caps.serve.allow("127.0.0.1:{port}", 8, 4096, 4096, 2000) '
            'let body = server.exchange("accepted") or return '
            "println(body) "
            "}"
        )
        result: dict[str, object] = {}

        def execute() -> None:
            result["value"] = _run_capture(source)

        thread = threading.Thread(target=execute, daemon=True)
        thread.start()

        body = b'{"b":2,"a":1}'
        request = (
            b"POST /orders HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"\r\n"
            + body
        )
        with _connect_when_ready(port, thread) as client:
            client.settimeout(2.0)
            client.sendall(request)
            response = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        thread.join(timeout=3.0)
        self.assertFalse(thread.is_alive(), "Koschei exchange did not finish")
        code, output, error = result["value"]
        self.assertEqual(code, 0, error)
        self.assertEqual(output, '{"b":2,"a":1}\n')
        self.assertEqual(error, "")
        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertTrue(response.endswith(b"\r\n\r\naccepted"), response)

    def test_manifest_attributes_exchange_operation_to_serve_domain(self) -> None:
        port = _free_loopback_port()
        program = parse(
            "fn main(caps: SystemCaps) { "
            f'let server = caps.serve.allow("127.0.0.1:{port}", 8, 4096, 4096, 2000) '
            'let body = server.exchange("ok") or return '
            "println(body) "
            "}"
        )
        check(program)
        manifest = analyze(program)
        self.assertIn("exchange", manifest.operations.get("serve", set()))
        self.assertEqual({grant.domain for grant in manifest.grants}, {"serve"})

    def test_response_wire_is_bounded_before_listener_is_opened(self) -> None:
        port = _free_loopback_port()
        code, output, error = _run_capture(
            "fn main(caps: SystemCaps) { "
            f'let server = caps.serve.allow("127.0.0.1:{port}", 1, 4096, 32, 500) '
            'let body = server.exchange("ok") or return '
            "println(body) "
            "}"
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("KS3410", error)
        self.assertIn("max_response_bytes", error)

    def test_accept_timeout_is_bounded_by_io_deadline(self) -> None:
        port = _free_loopback_port()
        started = time.monotonic()
        code, output, error = _run_capture(
            "fn main(caps: SystemCaps) { "
            f'let server = caps.serve.allow("127.0.0.1:{port}", 1, 4096, 4096, 150) '
            'let body = server.exchange("ok") or return '
            "println(body) "
            "}"
        )
        elapsed = time.monotonic() - started
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("KS3411", error)
        self.assertLess(elapsed, 2.0)

    def test_transfer_encoding_and_conflicting_content_length_are_rejected(self) -> None:
        from koschei.interpreter import KsError
        from koschei.serve_loopback_exchange_v1 import _parse_request_head

        chunked = _parse_request_head(
            b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        )
        self.assertIsInstance(chunked, KsError)
        self.assertIn("KS3410", chunked.message)

        conflicting = _parse_request_head(
            b"POST / HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n"
        )
        self.assertIsInstance(conflicting, KsError)
        self.assertIn("KS3410", conflicting.message)

    def test_exchange_diagnostics_are_explainable(self) -> None:
        for code in ("KS3410", "KS3411"):
            self.assertIn(code, CATALOG)
            self.assertIn(code, ENGLISH_CATALOG)


if __name__ == "__main__":
    unittest.main()
