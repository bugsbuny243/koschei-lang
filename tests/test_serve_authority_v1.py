from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze, render
from koschei.codegen_go import CodegenError, GoCodegen
from koschei.diagnostics import CATALOG, ENGLISH_CATALOG
from koschei.interpreter import run
from koschei.parser import parse
from koschei.semantic import SemanticError, check


POLICY = 'caps.serve.allow("127.0.0.1:8080", 64, 65536, 65536, 5000)'


class ServeAuthorityV1Tests(unittest.TestCase):
    def checked(self, source: str):
        program = parse(source)
        check(program)
        return program

    def test_exact_loopback_policy_is_a_sensitive_runtime_token(self) -> None:
        source = (
            "fn accept(server: ServeCaps) {} "
            "fn main(caps: SystemCaps) { "
            f"let server = {POLICY} "
            "accept(server) "
            "}"
        )
        program = self.checked(source)

        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = run(program, [])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "")

    def test_manifest_records_bind_and_all_budgets_exactly(self) -> None:
        program = self.checked(
            "fn main(caps: SystemCaps) { "
            f"let server = {POLICY} "
            "}"
        )
        manifest = analyze(program)
        self.assertEqual(manifest.domains(), ["serve"])
        self.assertTrue(manifest.is_exact)
        self.assertEqual(len(manifest.grants), 1)
        grant = manifest.grants[0]
        self.assertEqual(grant.domain, "serve")
        self.assertEqual(
            grant.scope,
            "127.0.0.1:8080 | connections=64 | request_bytes=65536 | "
            "response_bytes=65536 | deadline_ms=5000",
        )
        text = render(manifest, "serve.ks")
        self.assertIn("HTTP SUNUCU", text)
        self.assertIn("connections=64", text)
        self.assertIn("request_bytes=65536", text)
        self.assertIn("deadline_ms=5000", text)

    def test_wildcard_public_bind_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2411"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                'let server = caps.serve.allow("0.0.0.0:8080", 64, 65536, 65536, 5000) '
                "}"
            )

    def test_dynamic_budget_is_rejected_for_exact_v1_policy(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2410"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                "let connections = 64 "
                'let server = caps.serve.allow("127.0.0.1:8080", connections, 65536, 65536, 5000) '
                "}"
            )

    def test_budget_ceiling_is_rejected(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2411"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                'let server = caps.serve.allow("127.0.0.1:8080", 5000, 65536, 65536, 5000) '
                "}"
            )

    def test_serve_root_cannot_be_laundered_through_list(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                "let root = caps.serve "
                "let hidden = [root] "
                "}"
            )

    def test_serve_capability_cannot_be_laundered_through_list(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2401"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                f"let server = {POLICY} "
                "let hidden = [server] "
                "}"
            )

    def test_listener_operation_remains_fail_closed(self) -> None:
        with self.assertRaisesRegex(SemanticError, "KS2404"):
            self.checked(
                "fn main(caps: SystemCaps) { "
                f"let server = {POLICY} "
                "server.listen() "
                "}"
            )

    def test_native_codegen_rejects_serve_until_listener_abi_is_sealed(self) -> None:
        program = self.checked(
            "fn main(caps: SystemCaps) { "
            f"let server = {POLICY} "
            "}"
        )
        with self.assertRaisesRegex(CodegenError, "KS4001"):
            GoCodegen(program).generate()

    def test_serve_diagnostics_are_explainable_in_both_catalogs(self) -> None:
        for code in ("KS2410", "KS2411"):
            self.assertIn(code, CATALOG)
            self.assertIn(code, ENGLISH_CATALOG)
            self.assertIn(code, CATALOG[code].render())
            self.assertIn(code, ENGLISH_CATALOG[code].render("en"))


if __name__ == "__main__":
    unittest.main()
