"""P0.1: emit a reproducible host-authority manifest from the actual catalog.

This is a specification/evidence gate, not a runtime sandbox.
"""
from __future__ import annotations

import json
import unittest

from koschei.stdlib_catalog import CATALOG, document, validate_catalog


class P0HostImportCatalogTests(unittest.TestCase):
    def test_host_authority_manifest_is_complete_and_deterministic(self) -> None:
        validate_catalog()
        payload = document()
        rows = [
            {
                "operation": f"{family.name}.{operation.name}",
                "status": operation.status,
                "capability": operation.capability,
                "required_budgets": list(operation.required_budgets),
                "enforced_budgets": list(operation.enforced_budgets),
            }
            for family in CATALOG
            for operation in family.operations
        ]
        self.assertEqual(len(rows), payload["summary"]["operations"])
        self.assertEqual(
            len(rows),
            sum(payload["summary"][status] for status in ("supported", "reserved", "planned")),
        )
        self.assertEqual(
            len({row["operation"] for row in rows}), len(rows),
            "Ambiguous family.operation identifiers cannot define a host ABI",
        )
        privileged = [row for row in rows if row["capability"] is not None]
        # No unsupported capability operation may be promoted into an import contract.
        candidates = [row for row in privileged if row["status"] == "supported"]
        self.assertTrue(all(row["capability"] for row in candidates))
        # A candidate import must be backed by both execution backends and
        # complete declared resource budgets, not just a catalog status string.
        for family in CATALOG:
            for operation in family.operations:
                if operation.capability is None or operation.status != "supported":
                    continue
                with self.subTest(operation=f"{family.name}.{operation.name}"):
                    self.assertTrue(operation.interpreter)
                    self.assertTrue(operation.native_go)
                    self.assertEqual(
                        set(operation.required_budgets),
                        set(operation.enforced_budgets),
                    )
        self.assertFalse(
            any(row["operation"] in {"process.run", "process.spawn"} for row in candidates),
            "Process execution must remain excluded from candidate host imports",
        )
        print("P0_STDLIB_MANIFEST " + json.dumps({
            "schema": payload["schema"],
            "summary": payload["summary"],
            "supported_capability_operations": candidates,
            "reserved_capability_operations": [
                row for row in privileged if row["status"] == "reserved"
            ],
        }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
