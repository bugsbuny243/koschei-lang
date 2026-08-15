from __future__ import annotations

import unittest

from koschei.interpreter import KsError
from koschei import stdlib_catalog
from koschei.serve_loopback_exchange_v1 import _parse_request_head


class ServeLoopbackHttpStrictV1Tests(unittest.TestCase):
    def assert_protocol_error(self, raw: bytes, fragment: str) -> None:
        result = _parse_request_head(raw)
        self.assertIsInstance(result, KsError)
        self.assertIn("KS3410", result.message)
        self.assertIn(fragment, result.message)

    def test_http11_requires_exactly_one_host(self) -> None:
        self.assert_protocol_error(
            b"GET / HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
            "exactly one Host",
        )
        self.assert_protocol_error(
            b"GET / HTTP/1.1\r\nHost: one\r\nHost: two\r\n\r\n",
            "exactly one Host",
        )

    def test_duplicate_content_length_is_rejected_even_when_equal(self) -> None:
        self.assert_protocol_error(
            b"POST / HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Length: 1\r\nContent-Length: 1\r\n\r\n",
            "duplicate Content-Length",
        )

    def test_transfer_encoding_is_always_rejected(self) -> None:
        self.assert_protocol_error(
            b"POST / HTTP/1.1\r\nHost: localhost\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n",
            "Transfer-Encoding",
        )

    def test_method_and_target_use_reduced_unambiguous_grammar(self) -> None:
        self.assert_protocol_error(
            b"M-SEARCH / HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "uppercase alphabetic",
        )
        self.assert_protocol_error(
            b"GET http://localhost/ HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "origin-form",
        )
        self.assert_protocol_error(
            b"GET /path#fragment HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "origin-form",
        )

    def test_header_names_and_values_reject_ambiguous_controls(self) -> None:
        self.assert_protocol_error(
            b"GET / HTTP/1.1\r\nHost : localhost\r\n\r\n",
            "header name",
        )
        self.assert_protocol_error(
            b"GET / HTTP/1.1\r\nHost: local\x00host\r\n\r\n",
            "control byte",
        )

    def test_serve_catalog_does_not_claim_cross_backend_support(self) -> None:
        stdlib_catalog.validate_catalog(stdlib_catalog.CATALOG)
        serve = next(family for family in stdlib_catalog.CATALOG if family.name == "serve")
        self.assertEqual(serve.status, "partial")
        exchange = next(operation for operation in serve.operations if operation.name == "exchange")
        self.assertEqual(exchange.status, "reserved")
        self.assertFalse(exchange.interpreter)
        self.assertFalse(exchange.native_go)
        self.assertTrue(exchange.security_sensitive)
        self.assertEqual(
            set(exchange.required_budgets),
            {"connections", "request_bytes", "response_bytes", "deadline"},
        )
        listen = next(operation for operation in serve.operations if operation.name == "listen")
        self.assertEqual(listen.status, "planned")


if __name__ == "__main__":
    unittest.main()
