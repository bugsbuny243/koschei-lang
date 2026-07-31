from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from koschei.stdlib_catalog import (
    CATALOG,
    SCHEMA,
    Family,
    Operation,
    document,
    main,
    validate_catalog,
)


EXPECTED_FAMILIES = {
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
}


def operation(family_name: str, operation_name: str) -> Operation:
    for family in CATALOG:
        if family.name != family_name:
            continue
        for item in family.operations:
            if item.name == operation_name:
                return item
    raise AssertionError(f"missing operation: {family_name}.{operation_name}")


class StandardLibraryCatalogTests(unittest.TestCase):
    def test_catalog_is_valid_and_has_the_complete_target_family_set(self) -> None:
        validate_catalog()
        payload = document()
        self.assertEqual(SCHEMA, "koschei.stdlib/v2")
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["summary"]["families"], 32)
        self.assertEqual({family.name for family in CATALOG}, EXPECTED_FAMILIES)

    def test_supported_never_means_one_backend_only(self) -> None:
        for family in CATALOG:
            for item in family.operations:
                with self.subTest(family=family.name, operation=item.name):
                    if item.status == "supported":
                        self.assertTrue(item.interpreter)
                        self.assertTrue(item.native_go)
                    else:
                        self.assertFalse(item.interpreter)
                        self.assertFalse(item.native_go)

    def test_enforced_budgets_are_always_declared_required(self) -> None:
        for family in CATALOG:
            for item in family.operations:
                with self.subTest(family=family.name, operation=item.name):
                    self.assertTrue(
                        set(item.enforced_budgets).issubset(item.required_budgets)
                    )

    def test_security_sensitive_support_requires_all_budgets_enforced(self) -> None:
        for family in CATALOG:
            for item in family.operations:
                if item.status != "supported" or not item.security_sensitive:
                    continue
                with self.subTest(family=family.name, operation=item.name):
                    self.assertEqual(
                        set(item.required_budgets), set(item.enforced_budgets)
                    )

        invalid = (
            Family(
                "unsafe",
                "partial",
                "v1",
                "test",
                (
                    Operation(
                        "read",
                        "supported",
                        interpreter=True,
                        native_go=True,
                        capability="DiskCaps",
                        required_budgets=("bytes",),
                        security_sensitive=True,
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "security-sensitive support lacks enforced budgets"
        ):
            validate_catalog(invalid)

    def test_reviewed_false_promises_are_reserved(self) -> None:
        for family_name, operation_name in (
            ("core", "print"),
            ("core", "println"),
            ("text", "to_int"),
            ("request", "get"),
            ("data", "parse_json"),
            ("disk", "read"),
            ("disk", "read_file"),
            ("disk", "write"),
            ("disk", "write_file"),
            ("disk", "list"),
            ("env", "get"),
            ("process", "run"),
            ("process", "spawn"),
        ):
            with self.subTest(family=family_name, operation=operation_name):
                self.assertEqual(
                    operation(family_name, operation_name).status, "reserved"
                )

    def test_partial_enforcement_is_visible_without_claiming_support(self) -> None:
        get = operation("request", "get")
        self.assertEqual(get.status, "reserved")
        self.assertEqual(set(get.enforced_budgets), {"deadline", "redirects"})
        self.assertEqual(
            set(get.required_budgets),
            {"deadline", "response_bytes", "redirects"},
        )

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
            for item in family.operations:
                with self.subTest(family=family.name, operation=item.name):
                    self.assertIsNotNone(item.capability)

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
        self.assertIn("fully_bounded_supported", parsed["summary"])
        request_get = next(
            item
            for family in parsed["families"]
            if family["name"] == "request"
            for item in family["operations"]
            if item["name"] == "get"
        )
        self.assertEqual(request_get["status"], "reserved")
        self.assertIn("response_bytes", request_get["required_budgets"])
        self.assertNotIn("response_bytes", request_get["enforced_budgets"])

    def test_human_report_names_security_counts(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([]), 0)
        text = output.getvalue()
        self.assertIn("supported=", text)
        self.assertIn("reserved=", text)
        self.assertIn("planned=", text)
        self.assertIn("fully_bounded_supported=", text)
        self.assertIn("data", text)
        self.assertIn("request", text)


if __name__ == "__main__":
    unittest.main()
