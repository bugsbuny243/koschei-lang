from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from koschei.stdlib_catalog import CATALOG, SCHEMA, document, main, validate_catalog


class StandardLibraryCatalogTests(unittest.TestCase):
    def test_catalog_is_valid_and_has_the_complete_target_family_set(self) -> None:
        validate_catalog()
        payload = document()
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["summary"]["families"], 32)
        self.assertEqual(
            {family.name for family in CATALOG},
            {
                "core",
                "result",
                "text",
                "list",
                "map",
                "data",
                "request",
                "serve",
                "disk",
                "env",
                "process",
                "clock",
                "log",
                "secure",
                "random",
                "identity",
                "encode",
                "config",
                "database",
                "test",
                "task",
                "channel",
                "stream",
                "tls",
                "cache",
                "queue",
                "metrics",
                "trace",
                "health",
                "compress",
                "dns",
                "websocket",
            },
        )

    def test_supported_never_means_one_backend_only(self) -> None:
        for family in CATALOG:
            for operation in family.operations:
                with self.subTest(family=family.name, operation=operation.name):
                    if operation.status == "supported":
                        self.assertTrue(operation.interpreter)
                        self.assertTrue(operation.native_go)
                    else:
                        self.assertFalse(operation.interpreter)
                        self.assertFalse(operation.native_go)

    def test_current_false_promises_are_explicitly_reserved(self) -> None:
        statuses = {
            (family.name, operation.name): operation.status
            for family in CATALOG
            for operation in family.operations
        }
        self.assertEqual(statuses[("data", "parse_json")], "reserved")
        for method in ("post", "put", "delete", "request"):
            self.assertEqual(statuses[("request", method)], "reserved")
        for method in ("run", "spawn"):
            self.assertEqual(statuses[("process", method)], "reserved")

    def test_effectful_target_families_name_their_authority(self) -> None:
        effectful = {
            "request",
            "serve",
            "disk",
            "env",
            "process",
            "clock",
            "log",
            "random",
            "config",
            "database",
            "task",
            "stream",
            "tls",
            "cache",
            "queue",
            "metrics",
            "trace",
            "health",
            "dns",
            "websocket",
        }
        for family in CATALOG:
            if family.name not in effectful:
                continue
            for operation in family.operations:
                with self.subTest(family=family.name, operation=operation.name):
                    self.assertIsNotNone(operation.capability)

    def test_json_output_is_deterministic_and_machine_readable(self) -> None:
        first = io.StringIO()
        second = io.StringIO()
        with redirect_stdout(first):
            self.assertEqual(main(["--json"]), 0)
        with redirect_stdout(second):
            self.assertEqual(main(["--json"]), 0)
        self.assertEqual(first.getvalue(), second.getvalue())
        parsed = json.loads(first.getvalue())
        self.assertEqual(parsed["schema"], SCHEMA)
        self.assertEqual(parsed["summary"]["families"], 32)

    def test_human_report_names_supported_reserved_and_planned_counts(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        text = output.getvalue()
        self.assertIn("supported=", text)
        self.assertIn("reserved=", text)
        self.assertIn("planned=", text)
        self.assertIn("data", text)
        self.assertIn("process", text)


if __name__ == "__main__":
    unittest.main()
