from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.runtime_boot_v1 import require_runtime_ready
from koschei.runtime_interpreter_bridge_v1 import install_canonical_authority_bridge


class RuntimeLegacyAuthorityQuarantineTests(unittest.TestCase):
    def setUp(self) -> None:
        require_runtime_ready(interpreter)

    def test_disk_read_caps_cannot_reach_legacy_write_surface(self) -> None:
        value = interpreter.DiskReadCaps(".")
        location = interpreter.SourceLocation(1, 1)
        with self.assertRaises(interpreter.KoscheiRuntimeError) as raised:
            interpreter.Interpreter._member(object(), value, "write", location)
        self.assertEqual(raised.exception.code, "KS3404")

    def test_narrowed_capability_cannot_reenter_legacy_allow_path(self) -> None:
        value = interpreter.NetCaps("https://example.com")
        location = interpreter.SourceLocation(1, 1)
        with self.assertRaises(interpreter.KoscheiRuntimeError) as raised:
            interpreter.Interpreter._member(object(), value, "allow", location)
        self.assertEqual(raised.exception.code, "KS3403")

    def test_bridge_reinstallation_is_idempotent_and_preserves_quarantine(self) -> None:
        before = interpreter.Interpreter._member
        install_canonical_authority_bridge(interpreter)
        after = interpreter.Interpreter._member
        self.assertIs(before, after)

        value = interpreter.DiskReadCaps(".")
        with self.assertRaises(interpreter.KoscheiRuntimeError):
            after(object(), value, "delete", interpreter.SourceLocation(1, 1))


if __name__ == "__main__":
    unittest.main()
