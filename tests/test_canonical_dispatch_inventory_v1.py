from __future__ import annotations

import inspect
import json
import unittest

from koschei import cli, cli_entry
from koschei.canonical_dispatch_inventory_v1 import (
    DispatchClass,
    DispatchInventoryError,
    INVENTORY,
    NATIVE_IR_MIGRATION_TARGET,
    PUBLIC_CANONICAL_EXECUTION_COMMANDS,
    compatibility_entrypoint_count,
    require_public_dispatch_classification,
    to_dict,
)
from koschei.object_space_native_ir_dispatch_v1 import (
    execute_authenticated_object_space_native_ir_v1,
    lower_authenticated_object_space_to_native_ir_v1,
)


class CanonicalDispatchInventoryV1Tests(unittest.TestCase):
    def test_public_check_run_build_are_explicitly_inventory_bound(self) -> None:
        parser = cli_entry.build_parser()
        subcommands = next(
            action
            for action in parser._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertTrue(
            PUBLIC_CANONICAL_EXECUTION_COMMANDS.issubset(subcommands.choices)
        )
        self.assertEqual(
            {entry.command for entry in INVENTORY},
            PUBLIC_CANONICAL_EXECUTION_COMMANDS,
        )

    def test_current_public_execution_debt_is_three_compat_entrypoints(self) -> None:
        self.assertEqual(compatibility_entrypoint_count(), 3)
        self.assertTrue(
            all(
                entry.classification is DispatchClass.COMPAT_MIGRATION_ONLY
                for entry in INVENTORY
            )
        )
        build = require_public_dispatch_classification("build")
        self.assertTrue(build.legacy_fallback)
        self.assertFalse(require_public_dispatch_classification("check").legacy_fallback)
        self.assertFalse(require_public_dispatch_classification("run").legacy_fallback)

    def test_unknown_execution_entrypoint_fails_closed(self) -> None:
        with self.assertRaises(DispatchInventoryError):
            require_public_dispatch_classification("native-looking-run")

    def test_classification_has_no_source_filename_or_parser_sniff_input(self) -> None:
        parameters = tuple(
            inspect.signature(require_public_dispatch_classification).parameters
        )
        self.assertEqual(parameters, ("command",))

    def test_check_inventory_matches_current_compatibility_pipeline(self) -> None:
        source = inspect.getsource(cli.command_check)
        self.assertIn("load_graph(", source)
        self.assertIn("check_graph(", source)
        self.assertIn("require_mir(graph)", source)

    def test_run_inventory_matches_current_compatibility_pipeline(self) -> None:
        source = inspect.getsource(cli_entry._run_with_public_budget)
        self.assertIn("_cli.open_graph(", source)
        self.assertIn("check_graph(graph)", source)
        self.assertIn("require_mir(graph)", source)
        self.assertIn("run_mir_with_budget(", source)

    def test_build_inventory_exposes_ast_go_compat_fallback(self) -> None:
        wrapper = inspect.getsource(cli_entry._build_with_public_lock)
        selector = inspect.getsource(cli_entry.native_build_mode)
        self.assertIn("native_build_mode(mir)", wrapper)
        self.assertIn('"mir_go_v1"', selector)
        self.assertIn('"ast_go_compat_v1"', selector)

    def test_native_ir_migration_target_is_real_and_has_no_legacy_loader_call(self) -> None:
        self.assertEqual(
            NATIVE_IR_MIGRATION_TARGET,
            "koschei.object_space_native_ir_dispatch_v1."
            "execute_authenticated_object_space_native_ir_v1",
        )
        execute_source = inspect.getsource(
            execute_authenticated_object_space_native_ir_v1
        )
        lower_source = inspect.getsource(lower_authenticated_object_space_to_native_ir_v1)
        self.assertIn("lower_authenticated_object_space_to_native_ir_v1", execute_source)
        self.assertIn("execute_native_ir_v1", execute_source)
        self.assertNotIn("load_authenticated_frontend_module_graph(", lower_source)
        self.assertIn("decode_authenticated_frontend_graph", lower_source)

    def test_machine_readable_snapshot_is_stable_json(self) -> None:
        first = to_dict()
        second = to_dict()
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True, separators=(",", ":"))
        self.assertIn("koschei.canonical-dispatch-inventory/v1", encoded)
        self.assertIn('"compatibility_entrypoint_count":3', encoded)


if __name__ == "__main__":
    unittest.main()
