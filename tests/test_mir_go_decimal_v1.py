"""Exact decimals in native binaries agree with ks run and the canonical MIR.

`ks build` refused decimal/decimal_add/decimal_sub/decimal_cmp/decimal_text
(KS4004). Every value and every KS3801-KS3803 message must match the Python
core (financial_decimal).
"""
from __future__ import annotations

import shutil
import unittest

from tests import test_mir_go_native_v2_parity as _parity

GO = shutil.which("go")

SOURCE = """
fn show(raw: String, scale: Int) {
    let value = decimal(raw, scale) or {
        println("error")
        return
    }
    println(decimal_text(value))
}

fn main() {
    let texts = ["101.25", "0", "-0.00", "-7.5", "0.0001", "12", "9223372036854775807",
        "-9223372036854775808", "9223372036854775808", "01.5", "1.", ".5", "+1", "1e3",
        " 1", "1.23456", "-", "١٢", "92233720368547758.08"]
    for text in texts {
        show(text, 4)
        show(text, 0)
    }
    show("1", 18)
    show("1", 19)
    show("1", -1)
    println(decimal("01.5", 2))
    println(decimal("1.234", 2))
    println(decimal("9223372036854775808", 0))
    println(decimal("1", 19))
    let a = decimal("9223372036854775.807", 3) or return
    let b = decimal("0.001", 3) or return
    let c = decimal("0.01", 2) or return
    println(decimal_add(a, b))
    println(decimal_sub(b, a))
    println(decimal_add(b, c))
    println(decimal_cmp(a, b))
    println(decimal_cmp(b, a))
    println(decimal_cmp(b, b))
    let low = decimal("-9223372036854775.808", 3) or return
    println(decimal_sub(low, b))
    println(decimal_add(low, b))
    println(low)
    println([b, a])
}
"""


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeDecimalTests(unittest.TestCase):
    workspace = _parity.MirGoNativeParityTests.workspace
    ks_run = _parity.MirGoNativeParityTests.ks_run
    canonical_run = _parity.MirGoNativeParityTests.canonical_run
    native_run = _parity.MirGoNativeParityTests.native_run
    assert_parity = _parity.MirGoNativeParityTests.assert_parity

    def test_decimals_match_both_executors(self) -> None:
        lines = self.assert_parity(SOURCE).splitlines()
        self.assertEqual(lines[:4], ["101.2500", "error", "0.0000", "0"])
        self.assertIn("KS3801: invalid decimal text", "\n".join(lines))
        self.assertIn("KS3802: decimal scales differ", "\n".join(lines))
        self.assertIn("KS3803: decimal addition overflow", "\n".join(lines))
        self.assertIn("KS3803: decimal subtraction overflow", "\n".join(lines))
        self.assertIn("-9223372036854775.808", lines)


if __name__ == "__main__":
    unittest.main()
