from __future__ import annotations

import unittest
from unittest.mock import patch

from koschei.interpreter import KsError
from koschei.serve_authority_v1 import ServeCaps, ServePolicy
from koschei.serve_loopback_exchange_v1 import _parse_request_head


class _FakeConnection:
    def __init__(self) -> None:
        self._chunks = [b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"]
        self.sent = b""
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, value) -> None:
        self.timeout = value

    def recv(self, size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def sendall(self, value: bytes) -> None:
        self.sent += value


class _FakeListener:
    def __init__(self) -> None:
        self.backlog = None
        self.bound = None
        self.timeout = None
        self.connection = _FakeConnection()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, value) -> None:
        self.timeout = value

    def bind(self, value) -> None:
        self.bound = value

    def listen(self, backlog: int) -> None:
        self.backlog = backlog

    def accept(self):
        return self.connection, ("127.0.0.1", 50000)


class ServeLoopbackExchangeParityV1Tests(unittest.TestCase):
    def test_http11_empty_host_is_rejected(self) -> None:
        result = _parse_request_head(
            b"GET / HTTP/1.1\r\nHost:    \r\n\r\n"
        )
        self.assertIsInstance(result, KsError)
        self.assertIn("KS3410", result.message)
        self.assertIn("Host", result.message)

    def test_interpreter_listener_uses_exact_capability_backlog(self) -> None:
        policy = ServePolicy(
            bind="127.0.0.1:8080",
            max_connections=257,
            max_request_bytes=4096,
            max_response_bytes=4096,
            deadline_ms=1000,
        )
        token = ServeCaps(policy)
        listener = _FakeListener()

        with patch(
            "koschei.serve_loopback_exchange_parity_v1.socket.socket",
            return_value=listener,
        ):
            body = token.exchange("ok")

        self.assertEqual(body, "")
        self.assertEqual(listener.bound, ("127.0.0.1", 8080))
        self.assertEqual(listener.backlog, 257)
        self.assertTrue(listener.connection.sent.endswith(b"\r\n\r\nok"))


if __name__ == "__main__":
    unittest.main()
