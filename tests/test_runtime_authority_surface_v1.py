from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import (
    NARROWED_OPERATIONS,
    ROOT_NARROWING,
    SYSTEM_CAPABILITY_MEMBERS,
)
from koschei.runtime_authority_surface_v1 import (
    capability_member_allowed,
    capability_members_for_type,
    runtime_capability_type_name,
    runtime_value_matches_capability,
)


class RuntimeAuthoritySurfaceTests(unittest.TestCase):
    def test_member_surface_is_derived_from_canonical_contract(self) -> None:
        self.assertEqual(
            capability_members_for_type("SystemCaps"),
            frozenset(SYSTEM_CAPABILITY_MEMBERS),
        )
        for type_name, methods in ROOT_NARROWING.items():
            self.assertEqual(capability_members_for_type(type_name), frozenset(methods))
        for type_name, methods in NARROWED_OPERATIONS.items():
            self.assertEqual(capability_members_for_type(type_name), frozenset(methods))

    def test_runtime_values_resolve_to_canonical_capability_names(self) -> None:
        samples = {
            "SystemCaps": interpreter.SystemCaps(),
            "NetRoot": interpreter.NetRoot(),
            "DiskRoot": interpreter.DiskRoot(),
            "EnvRoot": interpreter.EnvRoot(),
            "ProcessRoot": interpreter.ProcessRoot(),
            "NetCaps": interpreter.NetCaps("https://example.com"),
            "DiskCaps": interpreter.DiskCaps("."),
            "DiskReadCaps": interpreter.DiskReadCaps("."),
            "EnvCaps": interpreter.EnvCaps("PATH"),
            "ProcessCaps": interpreter.ProcessCaps("echo"),
        }
        for expected, value in samples.items():
            self.assertEqual(runtime_capability_type_name(interpreter, value), expected)
            self.assertTrue(runtime_value_matches_capability(interpreter, value, expected))

    def test_capability_member_policy_rejects_noncanonical_members(self) -> None:
        net = interpreter.NetRoot()
        self.assertTrue(capability_member_allowed(interpreter, net, "allow"))
        self.assertFalse(capability_member_allowed(interpreter, net, "request"))
        narrowed = interpreter.NetCaps("https://example.com")
        self.assertTrue(capability_member_allowed(interpreter, narrowed, "request"))
        self.assertFalse(capability_member_allowed(interpreter, narrowed, "allow"))

    def test_non_capability_value_never_gains_authority_surface(self) -> None:
        self.assertIsNone(runtime_capability_type_name(interpreter, "NetCaps"))
        self.assertFalse(capability_member_allowed(interpreter, "NetCaps", "request"))


if __name__ == "__main__":
    unittest.main()
