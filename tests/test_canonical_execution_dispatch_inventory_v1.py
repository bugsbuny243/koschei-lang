from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from koschei import cli_entry
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_native_ir_dispatch_v1 import (
    ObjectSpaceNativeIrDispatchError,
    execute_authenticated_object_space_native_ir_v1,
)
from koschei.object_space_v1 import ObjectSpaceProject, ObjectSpaceRecord


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "contracts" / "canonical-execution-dispatch-v1.json"
CLASSIFICATIONS = {
    "NATIVE_IR",
    "COMPAT_MIGRATION_ONLY",
    "FAIL_CLOSED_UNMIGRATED",
}
PROJECT_ID = bytes.fromhex("11" * 16)
ROOT_ID = bytes.fromhex("22" * 16)
LOCATOR = bytes.fromhex("33" * 32)


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _resolve_callable(identifier: str):
    module_name, qualname = identifier.split(":", 1)
    value = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    return value


def _native_project(source: bytes, *, root: Path = Path("/sealed/koschei")) -> ObjectSpaceProject:
    digest = hashlib.sha256(source).digest()
    secret = encode_authenticated_frontend_graph_secret(
        project_id=PROJECT_ID,
        root_object_id=ROOT_ID,
        objects={ROOT_ID: source},
        frontend_by_object={ROOT_ID: NATIVE_WITNESS_FRONTEND_V1},
    )
    return ObjectSpaceProject(
        root=root,
        project_id=PROJECT_ID,
        epoch=7,
        root_object_id=ROOT_ID,
        records=(ObjectSpaceRecord(ROOT_ID, digest, LOCATOR),),
        graph_secret=secret,
        object_payloads={ROOT_ID: source},
        unreferenced_locators=(),
    )


class CanonicalExecutionDispatchInventoryV1Tests(unittest.TestCase):
    def test_inventory_is_machine_readable_and_exactly_classified(self) -> None:
        inventory = _inventory()
        self.assertEqual(
            inventory["schema"],
            "koschei.canonical-execution-dispatch/v1",
        )
        entries = inventory["entrypoints"]
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(entries)
        for entry in entries:
            self.assertIn(entry["classification"], CLASSIFICATIONS)
            self.assertIn(entry["kind"], {"run", "check", "build"})
            self.assertTrue(entry["callable"])
            self.assertTrue(callable(_resolve_callable(entry["callable"])))

    def test_public_cli_run_check_build_are_all_in_inventory(self) -> None:
        parser = cli_entry.build_parser()
        subcommands = next(
            action
            for action in parser._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        canonical_commands = {"run", "check", "build"}
        self.assertTrue(canonical_commands.issubset(set(subcommands.choices)))

        entries = _inventory()["entrypoints"]
        classified_cli = {
            entry["kind"]
            for entry in entries
            if entry["surface"] == "CLI"
        }
        self.assertEqual(classified_cli, canonical_commands)

    def test_native_dispatch_apis_are_explicitly_inventory_bound(self) -> None:
        low_level_module = importlib.import_module(
            "koschei.object_space_native_ir_dispatch_v1"
        )
        canonical_module = importlib.import_module(
            "koschei.canonical_native_entrypoints_v1"
        )
        expected_native = {
            f"{low_level_module.__name__}:execute_authenticated_object_space_native_ir_v1",
            f"{canonical_module.__name__}:check_canonical_native_v1",
            f"{canonical_module.__name__}:run_canonical_native_v1",
        }
        inventory_native = {
            entry["callable"]
            for entry in _inventory()["entrypoints"]
            if entry["classification"] == "NATIVE_IR"
        }
        self.assertEqual(inventory_native, expected_native)

    def test_authenticated_native_input_ignores_filename_sniff_and_legacy_parser(self) -> None:
        project = _native_project(
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n",
            root=Path("/looks-like-a-legacy-project/main.ks"),
        )
        with (
            patch(
                "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
                side_effect=AssertionError("legacy Object Space ModuleGraph fallback reached"),
            ),
            patch(
                "koschei.modules.load_graph",
                side_effect=AssertionError("filename/source compatibility graph sniff reached"),
            ),
            patch(
                "koschei.parser.parse",
                side_effect=AssertionError("legacy parser coincidence reached"),
            ),
        ):
            authority = execute_authenticated_object_space_native_ir_v1(project)
        self.assertEqual(authority.value.value, 42)

    def test_unsupported_object_space_schema_fails_closed_even_for_native_source(self) -> None:
        source = b"witness answer 42\nresolve answer\n"
        project = ObjectSpaceProject(
            root=Path("/native-looking/main.ks"),
            project_id=PROJECT_ID,
            epoch=7,
            root_object_id=ROOT_ID,
            records=(ObjectSpaceRecord(ROOT_ID, hashlib.sha256(source).digest(), LOCATOR),),
            graph_secret=b"unsupported-authenticated-schema-shape",
            object_payloads={ROOT_ID: source},
            unreferenced_locators=(),
        )
        with (
            patch(
                "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
                side_effect=AssertionError("legacy Object Space fallback reached"),
            ),
            patch(
                "koschei.modules.load_graph",
                side_effect=AssertionError("legacy graph fallback reached"),
            ),
            patch(
                "koschei.parser.parse",
                side_effect=AssertionError("legacy parser fallback reached"),
            ),
        ):
            with self.assertRaises(ObjectSpaceNativeIrDispatchError):
                execute_authenticated_object_space_native_ir_v1(project)

    def test_remaining_compatibility_entrypoint_count_is_reported(self) -> None:
        entries = _inventory()["entrypoints"]
        remaining = sum(
            entry["classification"] == "COMPAT_MIGRATION_ONLY"
            for entry in entries
        )
        self.assertEqual(remaining, 6)
        print(
            "KOSCHEI DISPATCH MIGRATION: "
            f"compatibility_entrypoints={remaining} total_entrypoints={len(entries)}"
        )


if __name__ == "__main__":
    unittest.main()
