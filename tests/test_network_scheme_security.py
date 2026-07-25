from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

from koschei.cli import main
from koschei.interpreter import KsError, NetCaps, run
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class NetworkSchemeSecurityTests(unittest.TestCase):
    def test_constant_file_origin_is_rejected_with_ks2405(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("file://localhost/tmp/secret.txt") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2405"):
            check(program)

    def test_constant_ftp_origin_is_rejected_with_ks2405(self) -> None:
        program = parse(
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("ftp://example.com/pub/data") '
            '}'
        )
        with self.assertRaisesRegex(SemanticError, "KS2405"):
            check(program)

    def test_constant_https_origin_is_accepted(self) -> None:
        check(
            parse(
                'fn main(caps: SystemCaps) { '
                'let net = caps.net.allow("https://api.example.com") '
                '}'
            )
        )

    def test_runtime_rejects_file_url_without_reading_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = pathlib.Path(directory) / "secret.txt"
            secret.write_text("FILE-BRIDGE-SECRET", encoding="utf-8")
            url = "file://localhost" + str(secret)
            result = NetCaps(url).get(url)

        self.assertIsInstance(result, KsError)
        self.assertIn("KS3402", result.message)
        self.assertNotIn("FILE-BRIDGE-SECRET", result.message)

    def test_dynamic_file_origin_is_blocked_by_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = pathlib.Path(directory) / "secret.txt"
            secret.write_text("DYNAMIC-FILE-SECRET", encoding="utf-8")
            url = "file://localhost" + str(secret)
            source = (
                'fn main(caps: SystemCaps) { '
                f'let origin = "{url}" '
                'let net = caps.net.allow(origin) '
                'let result = net.get(origin) or "engellendi" '
                'println(result) '
                '}'
            )
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = run(parse(source), [])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "engellendi\n")
        self.assertEqual(error.getvalue(), "")
        self.assertNotIn("DYNAMIC-FILE-SECRET", output.getvalue())

    def test_http_opener_contains_no_cross_scheme_handlers(self) -> None:
        handlers = NetCaps("https://api.example.com")._opener.handlers
        forbidden = (
            urllib.request.FileHandler,
            urllib.request.FTPHandler,
            urllib.request.DataHandler,
        )
        for handler in handlers:
            self.assertNotIsInstance(handler, forbidden)

    def test_caps_command_rejects_file_origin_before_manifest(self) -> None:
        source = (
            'fn main(caps: SystemCaps) { '
            'let net = caps.net.allow("file://localhost/tmp/secret.txt") '
            '}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "attack.ks"
            path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            error = io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = main(["caps", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("KS2405", error.getvalue())
        self.assertNotIn("DİSK: yok", output.getvalue())


if __name__ == "__main__":
    unittest.main()
