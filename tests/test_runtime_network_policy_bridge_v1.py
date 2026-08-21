from __future__ import annotations

import unittest

from koschei import interpreter
from koschei.capability_effect_contract_v1 import NET_ORIGIN_SCHEMES
from koschei.runtime_boot_v1 import require_runtime_ready


class RuntimeNetworkPolicyBridgeTests(unittest.TestCase):
    def test_boot_binds_exact_canonical_policy_object(self) -> None:
        interpreter.ALLOWED_NET_SCHEMES = frozenset({"http", "https"})
        self.assertIsNot(interpreter.ALLOWED_NET_SCHEMES, NET_ORIGIN_SCHEMES)
        require_runtime_ready(interpreter)
        self.assertIs(interpreter.ALLOWED_NET_SCHEMES, NET_ORIGIN_SCHEMES)

    def test_mutated_policy_is_rebound_on_next_boot(self) -> None:
        require_runtime_ready(interpreter)
        interpreter.ALLOWED_NET_SCHEMES = frozenset({"file"})
        require_runtime_ready(interpreter)
        self.assertIs(interpreter.ALLOWED_NET_SCHEMES, NET_ORIGIN_SCHEMES)


if __name__ == "__main__":
    unittest.main()
