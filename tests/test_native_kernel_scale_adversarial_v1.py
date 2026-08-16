from __future__ import annotations

import unittest

from koschei.native_kernel_v1 import (
    MAX_WITNESSES,
    NativeKernelError,
    dependency_order,
    evaluate_native_kernel,
    parse_native_kernel,
)


class NativeKernelScaleAdversarialV1Tests(unittest.TestCase):
    def test_full_4096_witness_chain_has_no_host_recursion_limit(self) -> None:
        lines = ["witness n0 1"]
        for index in range(1, MAX_WITNESSES):
            lines.append(f"witness n{index} sum n{index - 1} 0")
        lines.append(f"resolve n{MAX_WITNESSES - 1}")
        source = "\n".join(lines) + "\n"

        kernel = parse_native_kernel(source)
        order = dependency_order(kernel)
        self.assertEqual(len(order), MAX_WITNESSES)
        self.assertEqual(order[0], "n0")
        self.assertEqual(order[-1], f"n{MAX_WITNESSES - 1}")
        self.assertEqual(evaluate_native_kernel(kernel), 1)

    def test_huge_decimal_token_fails_with_koschei_error_before_host_int_parser(self) -> None:
        enormous = "9" * 10_000
        source = f"witness answer {enormous}\nresolve answer\n"
        with self.assertRaises(NativeKernelError) as caught:
            parse_native_kernel(source)
        self.assertEqual(caught.exception.code, "KN1201")

    def test_leading_zero_decimal_aliases_are_not_canonical_source(self) -> None:
        for spelling in ("00", "01", "0000000000000000001"):
            with self.subTest(spelling=spelling):
                source = f"witness answer {spelling}\nresolve answer\n"
                with self.assertRaises(NativeKernelError) as caught:
                    parse_native_kernel(source)
                self.assertEqual(caught.exception.code, "KN1200")

    def test_single_zero_is_the_only_zero_literal_spelling(self) -> None:
        kernel = parse_native_kernel("witness answer 0\nresolve answer\n")
        self.assertEqual(evaluate_native_kernel(kernel), 0)

    def test_max_int64_decimal_boundary_is_admitted_exactly(self) -> None:
        maximum = (1 << 63) - 1
        kernel = parse_native_kernel(f"witness answer {maximum}\nresolve answer\n")
        self.assertEqual(evaluate_native_kernel(kernel), maximum)

    def test_one_past_max_int64_decimal_boundary_is_rejected_before_conversion(self) -> None:
        source = f"witness answer {1 << 63}\nresolve answer\n"
        with self.assertRaises(NativeKernelError) as caught:
            parse_native_kernel(source)
        self.assertEqual(caught.exception.code, "KN1201")


if __name__ == "__main__":
    unittest.main()
