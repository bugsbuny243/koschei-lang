from __future__ import annotations

import unittest

from koschei import semantic
from koschei.capability_effect_contract_v1 import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    NET_ORIGIN_SCHEMES,
    NARROWING_METHODS,
    ROOT_CAPABILITY_TYPES,
    legacy_narrowed_operations,
    legacy_root_narrowing,
    legacy_system_capability_members,
)
from koschei.semantic_contract_consumer_v1 import check


class SemanticContractConsumerTests(unittest.TestCase):
    def test_import_installs_canonical_compatibility_views(self) -> None:
        self.assertEqual(semantic.CAPABILITY_MEMBERS, legacy_system_capability_members())
        self.assertEqual(semantic.ROOT_METHODS, legacy_root_narrowing())
        self.assertEqual(semantic.NARROWED_METHODS, legacy_narrowed_operations())
        self.assertEqual(set(semantic.NARROWING_METHODS), set(NARROWING_METHODS))
        self.assertEqual(set(semantic.GUARDED_METHODS), set(GUARDED_METHODS))
        self.assertEqual(set(semantic.CAPABILITY_TYPES), set(CAPABILITY_TYPES))
        self.assertEqual(set(semantic.ROOT_CAPABILITY_TYPES), set(ROOT_CAPABILITY_TYPES))
        self.assertEqual(semantic.NET_ORIGIN_SCHEMES, NET_ORIGIN_SCHEMES)

    def test_each_check_repairs_mutated_legacy_views_before_analysis(self) -> None:
        original = semantic.check
        observed = {}

        def probe(program, imports=None):
            observed["members"] = dict(semantic.CAPABILITY_MEMBERS)
            observed["roots"] = {
                name: dict(methods) for name, methods in semantic.ROOT_METHODS.items()
            }
            observed["narrowed"] = {
                name: set(methods) for name, methods in semantic.NARROWED_METHODS.items()
            }
            return "sentinel"

        semantic.CAPABILITY_MEMBERS = {"evil": "Root"}
        semantic.ROOT_METHODS = {"Root": {"steal": "AllCaps"}}
        semantic.NARROWED_METHODS = {"AllCaps": {"exfiltrate"}}
        semantic.check = probe
        try:
            self.assertEqual(check(object(), {}), "sentinel")
        finally:
            semantic.check = original

        self.assertEqual(observed["members"], legacy_system_capability_members())
        self.assertEqual(observed["roots"], legacy_root_narrowing())
        self.assertEqual(observed["narrowed"], legacy_narrowed_operations())


if __name__ == "__main__":
    unittest.main()
