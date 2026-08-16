from __future__ import annotations

import unittest

from koschei.native_decision_realities_v1 import (
    NativeDecisionRealityError,
    check_native_decision_reality,
)


class NativeDecisionRealitiesScaleV1Tests(unittest.TestCase):
    def test_full_4096_structural_witness_frontier_has_smaller_active_reality(self) -> None:
        lines = [
            "witness gate truth yes",
            "witness chosen 1",
            "witness rejected 2",
            "witness s0 settle gate chosen rejected",
        ]
        for index in range(1, 4093):
            lines.append(f"witness s{index} settle gate s{index - 1} rejected")
        lines.append("resolve s4092")

        checked = check_native_decision_reality("\n".join(lines) + "\n")
        self.assertEqual(len(checked.graph.witnesses), 4096)
        self.assertEqual(len(checked.structural_order), 4096)
        self.assertEqual(len(checked.active_order), 4095)
        self.assertNotIn("rejected", checked.active_order)
        self.assertEqual(checked.value.value, 1)

    def test_4097th_structural_witness_is_rejected(self) -> None:
        lines = [
            "witness gate truth yes",
            "witness chosen 1",
            "witness rejected 2",
            "witness s0 settle gate chosen rejected",
        ]
        for index in range(1, 4094):
            lines.append(f"witness s{index} settle gate s{index - 1} rejected")
        lines.append("resolve s4093")
        with self.assertRaisesRegex(NativeDecisionRealityError, "exceeds 4096 witnesses"):
            check_native_decision_reality("\n".join(lines) + "\n")

    def test_deep_nested_decision_chain_avoids_host_recursion(self) -> None:
        lines = [
            "witness gate truth yes",
            "witness selected 42",
            "witness rejected 7",
            "witness s0 settle gate selected rejected",
        ]
        for index in range(1, 3000):
            lines.append(f"witness s{index} settle gate s{index - 1} rejected")
        lines.append("resolve s2999")
        checked = check_native_decision_reality("\n".join(lines) + "\n")
        self.assertEqual(checked.value.value, 42)
        self.assertEqual(len(checked.active_order), 3002)


if __name__ == "__main__":
    unittest.main()
