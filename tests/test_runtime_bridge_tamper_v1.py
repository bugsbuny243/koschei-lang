from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.runtime_boot_v1 import RuntimeBootError, require_runtime_ready


class RuntimeBridgeTamperV1Tests(unittest.TestCase):
    def test_repeated_boot_rejects_modified_canonical_bridge(self) -> None:
        require_runtime_ready(interpreter)
        interpreter_type = interpreter.Interpreter
        canonical_member = interpreter_type._canonical_member_v1
        canonical_matches = interpreter_type._canonical_matches_v1
        canonical_type_name = interpreter_type._canonical_type_name_v1

        def compromised_member(self, receiver, name, location):
            return getattr(receiver, name)

        interpreter_type._member = compromised_member
        try:
            with self.assertRaises(RuntimeBootError):
                require_runtime_ready(interpreter)
        finally:
            interpreter_type._member = canonical_member
            interpreter_type._runtime_matches_type = canonical_matches
            interpreter_type._runtime_type_name = staticmethod(canonical_type_name)

        # Restored bridge must be accepted again; the test cannot poison the
        # process for later runtime tests.
        require_runtime_ready(interpreter)


if __name__ == "__main__":
    unittest.main()
