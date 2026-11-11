from __future__ import annotations

import unittest

from koschei import native_value_domains_v1 as base
from koschei.native_signal_reality_v1 import (
    NativeSignalRealityError,
    evaluate_native_signal_reality_v1,
)


class NativeSignalRealityV1Tests(unittest.TestCase):
    def test_runtime_signal_composes_into_native_graph(self) -> None:
        source = (
            "witness price signal 0\n"
            "witness fee 2\n"
            "witness total sum price fee\n"
            "resolve total\n"
        )
        value = evaluate_native_signal_reality_v1(
            source,
            {0: base.NativeValue(base.WHOLE, 40)},
        )
        self.assertEqual(value.domain, base.WHOLE)
        self.assertEqual(value.value, 42)

    def test_signal_slot_order_is_not_semantic(self) -> None:
        first = (
            "witness left signal 9\n"
            "witness right signal 2\n"
            "witness total sum left right\n"
            "resolve total\n"
        )
        second = (
            "witness right signal 2\n"
            "witness total sum left right\n"
            "resolve total\n"
            "witness left signal 9\n"
        )
        bindings = {
            2: base.NativeValue(base.WHOLE, 2),
            9: base.NativeValue(base.WHOLE, 40),
        }
        self.assertEqual(
            evaluate_native_signal_reality_v1(first, bindings),
            evaluate_native_signal_reality_v1(second, bindings),
        )

    def test_missing_or_extra_signal_binding_fails_closed(self) -> None:
        source = "witness value signal 0\nresolve value\n"
        with self.assertRaises(NativeSignalRealityError):
            evaluate_native_signal_reality_v1(source, {})
        with self.assertRaises(NativeSignalRealityError):
            evaluate_native_signal_reality_v1(
                source,
                {
                    0: base.NativeValue(base.WHOLE, 1),
                    1: base.NativeValue(base.WHOLE, 2),
                },
            )

    def test_duplicate_signal_slot_is_rejected(self) -> None:
        source = (
            "witness a signal 7\n"
            "witness b signal 7\n"
            "witness total sum a b\n"
            "resolve total\n"
        )
        with self.assertRaises(NativeSignalRealityError):
            evaluate_native_signal_reality_v1(
                source,
                {7: base.NativeValue(base.WHOLE, 3)},
            )

    def test_signal_domain_cannot_be_coerced_by_operation(self) -> None:
        source = (
            "witness input signal 0\n"
            "witness fee 2\n"
            "witness total sum input fee\n"
            "resolve total\n"
        )
        with self.assertRaises(NativeSignalRealityError):
            evaluate_native_signal_reality_v1(
                source,
                {0: base.NativeValue(base.GLYPHS, "40")},
            )

    def test_ambient_input_syntax_is_not_a_signal(self) -> None:
        for source in (
            "witness x input()\nresolve x\n",
            "witness x argv 0\nresolve x\n",
            "witness x env HOME\nresolve x\n",
            "witness x stdin\nresolve x\n",
        ):
            with self.assertRaises(NativeSignalRealityError):
                evaluate_native_signal_reality_v1(source, {})

    def test_dormant_signal_is_rejected(self) -> None:
        source = (
            "witness used signal 0\n"
            "witness hidden signal 1\n"
            "resolve used\n"
        )
        with self.assertRaises(NativeSignalRealityError):
            evaluate_native_signal_reality_v1(
                source,
                {
                    0: base.NativeValue(base.WHOLE, 1),
                    1: base.NativeValue(base.WHOLE, 2),
                },
            )


if __name__ == "__main__":
    unittest.main()
