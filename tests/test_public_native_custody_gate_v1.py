from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from koschei.cli_entry import (
    _emit_go_from_sealed_mir,
    _native_custody_message,
    native_build_mode,
)


class PublicNativeCustodyGateTests(unittest.TestCase):
    def test_native_build_mode_blocks_legacy_ambient_backend(self) -> None:
        unsupported = SimpleNamespace(supported=False, reasons=("AST fallback remains",))
        with patch("koschei.cli_entry.inspect_mir_go_support", return_value=unsupported):
            self.assertEqual(
                native_build_mode(object()),
                "blocked_ambient_ast_go_v1",
            )

    def test_native_build_mode_allows_strict_mir_go(self) -> None:
        supported = SimpleNamespace(supported=True, reasons=())
        with patch("koschei.cli_entry.inspect_mir_go_support", return_value=supported):
            self.assertEqual(native_build_mode(object()), "mir_go_v1")

    def test_public_emit_go_fails_closed_before_legacy_codegen(self) -> None:
        graph = object()
        mir = object()
        unsupported = SimpleNamespace(
            supported=False,
            reasons=("member access is not MIR-Go yet",),
        )
        args = argparse.Namespace(source="demo.ks", lang="en")
        stderr = io.StringIO()

        with (
            patch("koschei.cli_entry._cli.open_graph", return_value=graph),
            patch("koschei.cli_entry.check_graph"),
            patch("koschei.cli_entry.require_mir", return_value=mir),
            patch("koschei.cli_entry.inspect_mir_go_support", return_value=unsupported),
            patch("koschei.cli_entry.generate_go_mir_native") as strict_codegen,
            redirect_stderr(stderr),
        ):
            result = _emit_go_from_sealed_mir(args)

        self.assertEqual(result, 1)
        self.assertIn("KS4004", stderr.getvalue())
        self.assertIn("filesystem/network/environment", stderr.getvalue())
        strict_codegen.assert_not_called()

    def test_public_emit_go_uses_only_strict_mir_go_when_supported(self) -> None:
        graph = object()
        mir = object()
        supported = SimpleNamespace(supported=True, reasons=())
        args = argparse.Namespace(source="demo.ks", lang="en")
        stdout = io.StringIO()

        with (
            patch("koschei.cli_entry._cli.open_graph", return_value=graph),
            patch("koschei.cli_entry.check_graph"),
            patch("koschei.cli_entry.require_mir", return_value=mir),
            patch("koschei.cli_entry.inspect_mir_go_support", return_value=supported),
            patch(
                "koschei.cli_entry.generate_go_mir_native",
                return_value="package main\n",
            ) as strict_codegen,
            redirect_stdout(stdout),
        ):
            result = _emit_go_from_sealed_mir(args)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "package main\n")
        strict_codegen.assert_called_once_with(mir)

    def test_custody_message_is_explicit_about_missing_boundary(self) -> None:
        message = _native_custody_message("en", ("unsupported member",))
        self.assertIn("separate capability broker", message)
        self.assertIn("OS confinement", message)
        self.assertIn("Use 'ks run'", message)


if __name__ == "__main__":
    unittest.main()
