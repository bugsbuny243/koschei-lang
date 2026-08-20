from __future__ import annotations

import types
import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import (
    NARROWED_OPERATIONS,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)
from koschei.runtime_capability_registry_v1 import (
    canonical_runtime_registry,
    validate_runtime_module,
)


class RuntimeCapabilityRegistryTests(unittest.TestCase):
    def test_interpreter_validates_against_canonical_registry(self) -> None:
        registry = validate_runtime_module(interpreter)
        self.assertEqual(dict(registry.system_members), dict(SYSTEM_CAPABILITY_MEMBERS))
        self.assertEqual(
            set(registry.capabilities),
            set(ROOT_NARROWING) | set(NARROWED_OPERATIONS),
        )

    def test_missing_runtime_method_fails_closed(self) -> None:
        fake = types.ModuleType("fake_runtime")

        class SystemCaps:
            __slots__ = tuple(SYSTEM_CAPABILITY_MEMBERS)

        fake.SystemCaps = SystemCaps
        for root_type in ROOT_NARROWING:
            setattr(fake, root_type, type(root_type, (), {}))
        for capability_type in NARROWED_OPERATIONS:
            setattr(fake, capability_type, type(capability_type, (), {}))

        with self.assertRaises(RuntimeError):
            validate_runtime_module(fake)

    def test_system_authority_surface_drift_fails_closed(self) -> None:
        fake = types.ModuleType("fake_runtime")

        class SystemCaps:
            __slots__ = tuple(SYSTEM_CAPABILITY_MEMBERS) + ("shadow",)

        fake.SystemCaps = SystemCaps
        with self.assertRaises(RuntimeError):
            validate_runtime_module(fake)

    def test_registry_is_derived_from_canonical_contract(self) -> None:
        registry = canonical_runtime_registry()
        for capability_type, methods in ROOT_NARROWING.items():
            self.assertEqual(registry.capabilities[capability_type].methods, frozenset(methods))
            self.assertTrue(registry.capabilities[capability_type].is_root)
        for capability_type, methods in NARROWED_OPERATIONS.items():
            self.assertEqual(registry.capabilities[capability_type].methods, frozenset(methods))
            self.assertFalse(registry.capabilities[capability_type].is_root)


if __name__ == "__main__":
    unittest.main()
