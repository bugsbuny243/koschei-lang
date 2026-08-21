from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.runtime_boot_v1 import RuntimeBootError, require_runtime_ready
from koschei.runtime_bridge_seal_v1 import runtime_bridge_fingerprint


class RuntimeBridgeSealTests(unittest.TestCase):
    def test_boot_pins_deterministic_bridge_fingerprint(self) -> None:
        require_runtime_ready(interpreter)
        first = runtime_bridge_fingerprint(interpreter)
        require_runtime_ready(interpreter)
        second = runtime_bridge_fingerprint(interpreter)
        self.assertEqual(first, second)

    def test_wrapper_code_drift_fails_closed(self) -> None:
        require_runtime_ready(interpreter)
        original = interpreter.Interpreter._runtime_type_name

        def compromised(value):
            return "ShadowCaps"

        try:
            interpreter.Interpreter._runtime_type_name = staticmethod(compromised)
            with self.assertRaises(RuntimeBootError):
                require_runtime_ready(interpreter)
        finally:
            interpreter.Interpreter._runtime_type_name = staticmethod(original)


if __name__ == "__main__":
    unittest.main()
