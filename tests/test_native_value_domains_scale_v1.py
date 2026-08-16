from __future__ import annotations

import unittest

from koschei.native_value_domains_v1 import (
    GLYPHS,
    NativeValueDomainError,
    check_native_value_domains,
)


class NativeValueDomainsScaleV1Tests(unittest.TestCase):
    def test_full_4096_whole_witness_chain_has_no_host_recursion_limit(self) -> None:
        lines = ["witness w0 1"]
        for index in range(1, 4096):
            lines.append(f"witness w{index} sum w{index - 1} 1")
        lines.append("resolve w4095")
        checked = check_native_value_domains("\n".join(lines) + "\n")
        self.assertEqual(len(checked.graph.witnesses), 4096)
        self.assertEqual(checked.value.value, 4096)

    def test_full_4096_glyph_merge_chain_is_bounded_and_deterministic(self) -> None:
        lines = [
            "witness unit glyphs 1 a",
            "witness w0 glyphs 1 a",
        ]
        for index in range(1, 4095):
            lines.append(f"witness w{index} merge w{index - 1} unit")
        lines.append("resolve w4094")
        checked = check_native_value_domains("\n".join(lines) + "\n")
        self.assertEqual(len(checked.graph.witnesses), 4096)
        self.assertEqual(checked.value.domain, GLYPHS)
        self.assertEqual(len(checked.value.value.encode("utf-8")), 4096)

    def test_glyph_result_budget_accepts_exact_limit_and_rejects_one_doubling_more(self) -> None:
        seed = "a" * 65536
        prefix = f"witness seed glyphs 65536 {seed}\n"
        exact = (
            prefix
            + "witness d1 merge seed seed\n"
            + "witness d2 merge d1 d1\n"
            + "witness d3 merge d2 d2\n"
            + "witness d4 merge d3 d3\n"
            + "resolve d4\n"
        )
        checked = check_native_value_domains(exact)
        self.assertEqual(len(checked.value.value.encode("utf-8")), 1 << 20)

        overflow = exact.replace(
            "resolve d4\n",
            "witness d5 merge d4 d4\nresolve d5\n",
        )
        with self.assertRaisesRegex(NativeValueDomainError, "exceeds result byte budget"):
            check_native_value_domains(overflow)

    def test_4097th_witness_is_rejected_by_language_limit(self) -> None:
        lines = ["witness w0 1"]
        for index in range(1, 4097):
            lines.append(f"witness w{index} sum w{index - 1} 1")
        lines.append("resolve w4096")
        with self.assertRaisesRegex(NativeValueDomainError, "exceeds 4096 witnesses"):
            check_native_value_domains("\n".join(lines) + "\n")


if __name__ == "__main__":
    unittest.main()
