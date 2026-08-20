from __future__ import annotations

import unittest

from koschei.capability_effect_contract_v1 import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    NARROWED_OPERATIONS,
    NARROWING_METHODS,
    NET_ORIGIN_SCHEMES,
    ROOT_CAPABILITY_TYPES,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)
from koschei import semantic


class SemanticCapabilityContractTests(unittest.TestCase):
    """Legacy semantic checker canonical capability contract'tan sapamaz.

    semantic.py henüz tamamen consumer'a indirgenmeden önce bu test migration
    kilididir: capability şekli, narrowing yüzeyi, guarded operation listesi ve
    network boundary policy tek canonical sözleşmeyle birebir aynı kalmalıdır.
    """

    def test_system_capability_members_match_canonical_contract(self) -> None:
        self.assertEqual(semantic.CAPABILITY_MEMBERS, dict(SYSTEM_CAPABILITY_MEMBERS))

    def test_root_narrowing_matches_canonical_contract(self) -> None:
        expected = {
            capability: dict(methods)
            for capability, methods in ROOT_NARROWING.items()
        }
        self.assertEqual(semantic.ROOT_METHODS, expected)

    def test_narrowed_operations_match_canonical_contract(self) -> None:
        expected = {
            capability: set(methods)
            for capability, methods in NARROWED_OPERATIONS.items()
        }
        self.assertEqual(semantic.NARROWED_METHODS, expected)

    def test_derived_capability_sets_match_canonical_contract(self) -> None:
        self.assertEqual(set(semantic.NARROWING_METHODS), set(NARROWING_METHODS))
        self.assertEqual(set(semantic.GUARDED_METHODS), set(GUARDED_METHODS))
        self.assertEqual(set(semantic.CAPABILITY_TYPES), set(CAPABILITY_TYPES))
        self.assertEqual(
            set(semantic.ROOT_CAPABILITY_TYPES),
            set(ROOT_CAPABILITY_TYPES),
        )

    def test_network_origin_policy_matches_canonical_contract(self) -> None:
        self.assertEqual(semantic.NET_ORIGIN_SCHEMES, NET_ORIGIN_SCHEMES)


if __name__ == "__main__":
    unittest.main()
