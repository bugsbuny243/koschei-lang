from __future__ import annotations

import unittest
from unittest.mock import patch

from koschei import cli


class CliRuntimeBootRouteTests(unittest.TestCase):
    def test_command_run_routes_checked_mir_through_boot_gate(self) -> None:
        graph = object()
        mir = object()

        with (
            patch.object(cli, "open_graph", return_value=graph) as open_graph,
            patch.object(cli, "check_graph") as check_graph,
            patch.object(cli, "require_mir", return_value=mir) as require_mir,
            patch.object(cli, "run_checked_mir", return_value=17) as run_checked_mir,
        ):
            result = cli.command_run("program.ks")

        self.assertEqual(result, 17)
        open_graph.assert_called_once_with("program.ks")
        check_graph.assert_called_once_with(graph)
        require_mir.assert_called_once_with(graph)
        run_checked_mir.assert_called_once_with(mir, [])

    def test_runtime_boot_error_is_part_of_cli_fail_closed_errors(self) -> None:
        with patch.object(
            cli,
            "command_run",
            side_effect=cli.RuntimeBootError("KOSCHEI RUNTIME BOOT DENIED: drift"),
        ):
            result = cli.main(["run", "program.ks"])

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
