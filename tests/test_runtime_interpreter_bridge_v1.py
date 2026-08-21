from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.runtime_interpreter_bridge_v1 import install_canonical_authority_bridge


class RuntimeInterpreterBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        install_canonical_authority_bridge(interpreter)

    def _runtime(self):
        program = type("Program", (), {"declarations": [], "structs": [], "enums": []})()
        return interpreter.Interpreter(program)

    def test_disk_read_caps_write_is_not_runtime_visible(self) -> None:
        runtime = self._runtime()
        value = interpreter.DiskReadCaps(".")
        with self.assertRaises(interpreter.KoscheiRuntimeError) as caught:
            runtime._member(value, "write", interpreter.SourceLocation(1, 1))
        self.assertEqual(caught.exception.code, "KS3404")

    def test_capability_type_name_uses_canonical_registry(self) -> None:
        self.assertEqual(
            interpreter.Interpreter._runtime_type_name(
                interpreter.NetCaps("https://example.com")
            ),
            "NetCaps",
        )
        self.assertEqual(
            interpreter.Interpreter._runtime_type_name(interpreter.ProcessRoot()),
            "ProcessRoot",
        )

    def test_capability_matching_uses_canonical_registry(self) -> None:
        runtime = self._runtime()
        self.assertTrue(runtime._runtime_matches_type(interpreter.EnvRoot(), ("EnvRoot",)))
        self.assertFalse(runtime._runtime_matches_type(interpreter.EnvRoot(), ("NetRoot",)))


if __name__ == "__main__":
    unittest.main()
