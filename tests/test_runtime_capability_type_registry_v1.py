from __future__ import annotations

import types
import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import CAPABILITY_TYPES
from koschei.runtime_capability_registry_v1 import (
    capability_type_name_for_value,
    runtime_capability_types,
    value_matches_capability_type,
)


class RuntimeCapabilityTypeRegistryTests(unittest.TestCase):
    def test_runtime_type_map_is_derived_from_canonical_type_names(self) -> None:
        resolved = runtime_capability_types(interpreter)
        self.assertEqual(set(resolved), set(CAPABILITY_TYPES))
        for type_name, runtime_type in resolved.items():
            self.assertIs(runtime_type, getattr(interpreter, type_name))

    def test_values_resolve_to_canonical_capability_type_names(self) -> None:
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
            self.assertEqual(
                capability_type_name_for_value(interpreter, value),
                expected,
            )
            self.assertTrue(
                value_matches_capability_type(interpreter, value, expected)
            )

    def test_non_capability_value_has_no_capability_name(self) -> None:
        self.assertIsNone(capability_type_name_for_value(interpreter, "hello"))
        self.assertFalse(
            value_matches_capability_type(interpreter, "hello", "NetCaps")
        )

    def test_missing_canonical_runtime_type_fails_closed(self) -> None:
        fake = types.ModuleType("fake_runtime")
        for type_name in CAPABILITY_TYPES:
            if type_name == "NetCaps":
                continue
            setattr(fake, type_name, getattr(interpreter, type_name))
        with self.assertRaises(RuntimeError):
            runtime_capability_types(fake)

    def test_runtime_cannot_add_new_canonical_type_by_defining_extra_class(self) -> None:
        fake = types.ModuleType("fake_runtime")
        for type_name in CAPABILITY_TYPES:
            setattr(fake, type_name, getattr(interpreter, type_name))
        fake.ShadowCaps = type("ShadowCaps", (), {})
        self.assertNotIn("ShadowCaps", runtime_capability_types(fake))


if __name__ == "__main__":
    unittest.main()
