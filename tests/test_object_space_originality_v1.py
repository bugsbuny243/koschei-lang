from __future__ import annotations

import unittest

from koschei.object_space_originality_v1 import OBJECT_SPACE_SCAFFOLD_PROVENANCE_V1
from koschei.originality_contract_v1 import audit_scaffold_surface


class ObjectSpaceOriginalityV1Tests(unittest.TestCase):
    def test_k0_k1_surface_passes_with_explicit_koschei_provenance(self) -> None:
        violations = audit_scaffold_surface(
            ["k0", "k1"],
            provenance=OBJECT_SPACE_SCAFFOLD_PROVENANCE_V1,
        )
        self.assertEqual(violations, ())

    def test_conventional_project_roles_are_not_canonical_object_space_paths(self) -> None:
        canonical = {"k0", "k1"}
        conventional = {
            "src",
            "main",
            "main.ks",
            "module",
            "modules",
            "package",
            "packages",
            "test",
            "tests",
            "config",
            "build",
            "dist",
            "target",
            "vendor",
            "lib",
        }
        self.assertTrue(canonical.isdisjoint(conventional))


if __name__ == "__main__":
    unittest.main()
