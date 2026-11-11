from __future__ import annotations

import unittest

from koschei.native_vow_reality_v1 import (
    NativeVowRealityError,
    check_native_vow_reality_v1,
)


class NativeVowRealityV1Tests(unittest.TestCase):
    def test_true_vow_admits_closed_decision_reality(self) -> None:
        source = (
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "vow gate\n"
            "resolve result\n"
        )
        checked = check_native_vow_reality_v1(source)
        self.assertEqual(checked.vows, ("gate",))
        self.assertEqual(checked.value.domain, "glyphs")
        self.assertEqual(checked.value.value, "ok")

    def test_vow_order_does_not_change_reality(self) -> None:
        first = (
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "vow gate\n"
            "resolve result\n"
        )
        second = (
            "vow gate\n"
            "witness rejected glyphs 2 no\n"
            "resolve result\n"
            "witness result settle gate accepted rejected\n"
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
        )
        left = check_native_vow_reality_v1(first)
        right = check_native_vow_reality_v1(second)
        self.assertEqual(left.value, right.value)
        self.assertEqual(set(left.vows), set(right.vows))

    def test_false_vow_fails_reality_admission(self) -> None:
        source = (
            "witness gate truth no\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "vow gate\n"
            "resolve result\n"
        )
        with self.assertRaisesRegex(NativeVowRealityError, "not satisfied"):
            check_native_vow_reality_v1(source)

    def test_vow_forbids_truth_coercion(self) -> None:
        source = (
            "witness amount 7\n"
            "witness sameamount same amount amount\n"
            "witness result settle sameamount amount amount\n"
            "vow amount\n"
            "resolve result\n"
        )
        with self.assertRaisesRegex(NativeVowRealityError, "truth witness"):
            check_native_vow_reality_v1(source)

    def test_unknown_and_duplicate_vows_fail_closed(self) -> None:
        unknown = (
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "vow ghost\n"
            "resolve result\n"
        )
        duplicate = (
            "witness gate truth yes\n"
            "witness accepted glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate accepted rejected\n"
            "vow gate\n"
            "vow gate\n"
            "resolve result\n"
        )
        with self.assertRaises(NativeVowRealityError):
            check_native_vow_reality_v1(unknown)
        with self.assertRaisesRegex(NativeVowRealityError, "duplicate vow"):
            check_native_vow_reality_v1(duplicate)

    def test_mainstream_exception_syntax_is_not_accepted(self) -> None:
        source = (
            "try {\n"
            "witness gate truth yes\n"
            "} catch {\n"
            "resolve gate\n"
        )
        with self.assertRaises(NativeVowRealityError):
            check_native_vow_reality_v1(source)


if __name__ == "__main__":
    unittest.main()
