from __future__ import annotations

import unittest

from koschei.native_kernel_v1 import NativeKernelError, check_native_kernel, parse_native_kernel


class NativeKernelAdversarialV1Tests(unittest.TestCase):
    def assert_code(self, source: str, code: str) -> None:
        with self.assertRaises(NativeKernelError) as caught:
            parse_native_kernel(source)
        self.assertEqual(caught.exception.code, code)

    def test_legacy_function_syntax_has_no_native_fallback(self) -> None:
        self.assert_code("fn main() { return 7 }\n", "KN1006")

    def test_legacy_binding_syntax_has_no_native_fallback(self) -> None:
        self.assert_code("let answer = 7\nresolve answer\n", "KN1006")

    def test_unicode_confusable_witness_word_is_rejected_before_tokenization(self) -> None:
        # Cyrillic small i in a word visually close to the native clause spelling.
        self.assert_code("wіtness answer 7\nresolve answer\n", "KN1001")

    def test_noncanonical_whitespace_is_rejected(self) -> None:
        self.assert_code(" witness answer 7\nresolve answer\n", "KN1003")
        self.assert_code("witness  answer 7\nresolve answer\n", "KN1003")
        self.assert_code("witness answer 7 \nresolve answer\n", "KN1003")
        self.assert_code("witness\tanswer 7\nresolve answer\n", "KN1003")
        self.assert_code("witness answer 7\r\nresolve answer\r\n", "KN1003")

    def test_missing_or_duplicate_resolve_fails_closed(self) -> None:
        self.assert_code("witness answer 7\n", "KN1103")
        self.assert_code(
            "witness answer 7\nresolve answer\nresolve answer\n",
            "KN1103",
        )

    def test_duplicate_witness_identity_fails_closed(self) -> None:
        self.assert_code(
            "witness answer 7\nwitness answer 8\nresolve answer\n",
            "KN1101",
        )

    def test_unknown_reference_fails_closed(self) -> None:
        self.assert_code(
            "witness answer sum missing 1\nresolve answer\n",
            "KN1105",
        )

    def test_cycle_fails_closed(self) -> None:
        self.assert_code(
            "witness left sum right 1\n"
            "witness right product left 2\n"
            "resolve left\n",
            "KN1106",
        )

    def test_dormant_witness_outside_resolved_reality_is_rejected(self) -> None:
        self.assert_code(
            "witness answer 7\n"
            "witness hidden 999\n"
            "resolve answer\n",
            "KN1107",
        )

    def test_reserved_native_and_legacy_words_cannot_be_identity(self) -> None:
        self.assert_code("witness sum 7\nresolve sum\n", "KN1004")
        self.assert_code("witness return 7\nresolve return\n", "KN1004")

    def test_infix_arithmetic_is_rejected_not_reinterpreted(self) -> None:
        self.assert_code(
            "witness left 7\n"
            "witness right 2\n"
            "witness answer left + right\n"
            "resolve answer\n",
            "KN1006",
        )

    def test_operation_arity_is_exact(self) -> None:
        self.assert_code("witness answer sum 1\nresolve answer\n", "KN1005")
        self.assert_code("witness answer product 1 2 3\nresolve answer\n", "KN1005")

    def test_int64_literal_and_computation_overflow_fail_closed(self) -> None:
        self.assert_code(
            f"witness answer {1 << 63}\nresolve answer\n",
            "KN1201",
        )
        with self.assertRaises(NativeKernelError) as caught:
            check_native_kernel(
                f"witness max {((1 << 63) - 1)}\n"
                "witness answer sum max 1\n"
                "resolve answer\n"
            )
        self.assertEqual(caught.exception.code, "KN1202")

    def test_identifier_grammar_rejects_case_underscore_and_non_ascii_aliases(self) -> None:
        self.assert_code("witness Answer 7\nresolve Answer\n", "KN1004")
        self.assert_code("witness answer_value 7\nresolve answer_value\n", "KN1004")
        self.assert_code("witness ölçüm 7\nresolve ölçüm\n", "KN1001")

    def test_blank_lines_and_missing_final_lf_are_noncanonical(self) -> None:
        self.assert_code("witness answer 7\n\nresolve answer\n", "KN1003")
        self.assert_code("witness answer 7\nresolve answer", "KN1003")


if __name__ == "__main__":
    unittest.main()
