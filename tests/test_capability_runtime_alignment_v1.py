from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import (
    CAPABILITY_METHOD_EFFECTS,
    NARROWED_OPERATIONS,
    NET_ORIGIN_SCHEMES,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)
from koschei.semantic import NET_ORIGIN_SCHEMES as SEMANTIC_NET_ORIGIN_SCHEMES


class CapabilityRuntimeAlignmentTests(unittest.TestCase):
    def test_system_caps_surface_matches_canonical_contract(self) -> None:
        self.assertEqual(
            frozenset(interpreter.SystemCaps.__slots__),
            frozenset(SYSTEM_CAPABILITY_MEMBERS),
        )
        for member, root_type in SYSTEM_CAPABILITY_MEMBERS.items():
            self.assertTrue(hasattr(interpreter, root_type), (member, root_type))

    def test_root_narrowing_methods_exist_in_runtime(self) -> None:
        for root_type, methods in ROOT_NARROWING.items():
            runtime_type = getattr(interpreter, root_type)
            for method, narrowed_type in methods.items():
                self.assertTrue(callable(getattr(runtime_type, method, None)))
                self.assertTrue(hasattr(interpreter, narrowed_type))

    def test_narrowed_operations_have_runtime_implementations(self) -> None:
        for capability_type, operations in NARROWED_OPERATIONS.items():
            runtime_type = getattr(interpreter, capability_type)
            for operation in operations:
                self.assertTrue(
                    callable(getattr(runtime_type, operation, None)),
                    f"{capability_type}.{operation} canonical contract'ta var ama runtime'da yok",
                )

    def test_every_runtime_contract_method_has_an_effect_identity(self) -> None:
        expected_types = set(ROOT_NARROWING) | set(NARROWED_OPERATIONS)
        self.assertEqual(set(CAPABILITY_METHOD_EFFECTS), expected_types)
        for root_type, methods in ROOT_NARROWING.items():
            self.assertEqual(set(CAPABILITY_METHOD_EFFECTS[root_type]), set(methods))
        for capability_type, operations in NARROWED_OPERATIONS.items():
            self.assertEqual(
                set(CAPABILITY_METHOD_EFFECTS[capability_type]),
                set(operations),
            )

    def test_network_boundary_policy_is_identical_across_layers(self) -> None:
        self.assertEqual(SEMANTIC_NET_ORIGIN_SCHEMES, NET_ORIGIN_SCHEMES)
        self.assertEqual(interpreter.ALLOWED_NET_SCHEMES, NET_ORIGIN_SCHEMES)


if __name__ == "__main__":
    unittest.main()
