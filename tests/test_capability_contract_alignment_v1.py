import unittest

from koschei import semantic
from koschei._typed_ops import method_type
from koschei.ast_nodes import SourceLocation
from koschei.capability_effect_contract_v1 import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    NARROWED_OPERATIONS,
    NARROWING_METHODS,
    ROOT_CAPABILITY_TYPES,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
    narrowed_type_for,
    operation_allowed,
)
from koschei.type_system import NamedType


class CapabilityContractAlignmentTests(unittest.TestCase):
    def test_legacy_semantic_tables_match_canonical_contract(self) -> None:
        self.assertEqual(semantic.CAPABILITY_MEMBERS, dict(SYSTEM_CAPABILITY_MEMBERS))
        self.assertEqual(
            semantic.ROOT_METHODS,
            {name: dict(methods) for name, methods in ROOT_NARROWING.items()},
        )
        self.assertEqual(
            semantic.NARROWED_METHODS,
            {name: set(methods) for name, methods in NARROWED_OPERATIONS.items()},
        )
        self.assertEqual(semantic.NARROWING_METHODS, set(NARROWING_METHODS))
        self.assertEqual(semantic.GUARDED_METHODS, set(GUARDED_METHODS))
        self.assertEqual(semantic.CAPABILITY_TYPES, set(CAPABILITY_TYPES))
        self.assertEqual(semantic.ROOT_CAPABILITY_TYPES, set(ROOT_CAPABILITY_TYPES))

    def test_narrowing_contract_is_total_for_declared_root_methods(self) -> None:
        for root, methods in ROOT_NARROWING.items():
            for method, narrowed in methods.items():
                self.assertEqual(narrowed_type_for(root, method), narrowed)
                self.assertIn(narrowed, CAPABILITY_TYPES)

    def test_every_narrowed_operation_has_explicit_membership(self) -> None:
        for capability, methods in NARROWED_OPERATIONS.items():
            for method in methods:
                self.assertTrue(operation_allowed(capability, method))

    def test_typed_hir_narrowing_consumes_canonical_contract(self) -> None:
        location = SourceLocation(1, 1)
        for root, methods in ROOT_NARROWING.items():
            for method, narrowed in methods.items():
                result = method_type(NamedType(root), method, (), location)
                self.assertEqual(result, NamedType(narrowed))


if __name__ == "__main__":
    unittest.main()
