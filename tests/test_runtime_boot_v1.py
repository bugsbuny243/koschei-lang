from __future__ import annotations

import types
import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import NET_ORIGIN_SCHEMES
from koschei.runtime_boot_v1 import RuntimeBootError, require_runtime_ready


class RuntimeBootGateTests(unittest.TestCase):
    def test_current_interpreter_passes_canonical_boot_gate(self) -> None:
        registry = require_runtime_ready(interpreter)
        self.assertEqual(registry.network_origin_schemes, NET_ORIGIN_SCHEMES)

    def test_network_policy_drift_fails_closed(self) -> None:
        original = interpreter.ALLOWED_NET_SCHEMES
        try:
            interpreter.ALLOWED_NET_SCHEMES = frozenset({"http", "https", "file"})
            with self.assertRaises(RuntimeBootError):
                require_runtime_ready(interpreter)
        finally:
            interpreter.ALLOWED_NET_SCHEMES = original

    def test_missing_system_caps_fails_closed(self) -> None:
        fake = types.ModuleType("fake_runtime")
        fake.ALLOWED_NET_SCHEMES = NET_ORIGIN_SCHEMES
        with self.assertRaises(RuntimeBootError):
            require_runtime_ready(fake)

    def test_extra_root_authority_surface_fails_closed(self) -> None:
        fake = types.ModuleType("fake_runtime")
        for name in (
            "NetRoot",
            "DiskRoot",
            "EnvRoot",
            "ProcessRoot",
            "NetCaps",
            "DiskCaps",
            "DiskReadCaps",
            "EnvCaps",
            "ProcessCaps",
        ):
            setattr(fake, name, getattr(interpreter, name))

        class CompromisedSystemCaps:
            __slots__ = ("net", "disk", "env", "process", "shadow")

        fake.SystemCaps = CompromisedSystemCaps
        fake.ALLOWED_NET_SCHEMES = NET_ORIGIN_SCHEMES
        with self.assertRaises(RuntimeBootError):
            require_runtime_ready(fake)


if __name__ == "__main__":
    unittest.main()
