from __future__ import annotations

import unittest
from unittest.mock import patch

from koschei.cli_entry import build_parser, main


class LspCliWiringTests(unittest.TestCase):
    def test_top_level_help_lists_lsp(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("lsp", help_text)
        self.assertIn("Language Server", help_text)

    def test_lsp_subcommand_dispatches_to_typed_server(self) -> None:
        with patch("koschei.cli_entry.command_lsp", return_value=17) as start_lsp:
            self.assertEqual(main(["lsp"]), 17)
        start_lsp.assert_called_once_with()

    def test_existing_commands_still_delegate_to_compiler_cli(self) -> None:
        with patch("koschei.cli_entry._cli.main", return_value=0) as compiler_main:
            self.assertEqual(main(["version"]), 0)
        compiler_main.assert_called_once_with(["version"])


if __name__ == "__main__":
    unittest.main()
