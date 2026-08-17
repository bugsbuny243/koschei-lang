from __future__ import annotations

import unittest

from koschei.capabilities import analyze
from koschei.interpreter import KsError, ServeCaps, SystemCaps
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class ServeAuthorityLoopbackCanonicalV1Tests(unittest.TestCase):
    def test_runtime_localhost_alias_is_sealed_as_literal_ipv4_loopback(self) -> None:
        token = SystemCaps().serve.allow("localhost:8080", 8, 4096, 4096, 1000)
        self.assertIsInstance(token, ServeCaps)
        self.assertEqual(token.policy.bind, "127.0.0.1:8080")

    def test_manifest_matches_canonical_runtime_endpoint(self) -> None:
        program = parse(
            "fn main(caps: SystemCaps) { "
            'let server = caps.serve.allow("localhost:8080", 8, 4096, 4096, 1000) '
            "}"
        )
        check(program)
        manifest = analyze(program)
        self.assertEqual(len(manifest.grants), 1)
        self.assertTrue(manifest.grants[0].scope.startswith("127.0.0.1:8080 |"))
        self.assertNotIn("localhost", manifest.grants[0].scope)

    def test_bracketed_ipv6_loopback_is_canonical_and_allowed(self) -> None:
        token = SystemCaps().serve.allow("[::1]:8080", 8, 4096, 4096, 1000)
        self.assertIsInstance(token, ServeCaps)
        self.assertEqual(token.policy.bind, "[::1]:8080")

    def test_unbracketed_ipv6_is_rejected_by_semantic_and_runtime_boundaries(self) -> None:
        program = parse(
            "fn main(caps: SystemCaps) { "
            'let server = caps.serve.allow("::1:8080", 8, 4096, 4096, 1000) '
            "}"
        )
        with self.assertRaisesRegex(SemanticError, "KS2411"):
            check(program)

        result = SystemCaps().serve.allow("::1:8080", 8, 4096, 4096, 1000)
        self.assertIsInstance(result, KsError)
        self.assertIn("KS2411", result.message)


if __name__ == "__main__":
    unittest.main()
