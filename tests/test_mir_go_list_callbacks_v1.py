"""Native List.sort/filter/find/map/any agree with ks run and the canonical MIR.

A callback is a top-level Koschei function of one parameter (a lambda lowers
to one), the same rule `ks run` applies (runtime_primitive_facade_v1). It is
passed to the method and never stored; any other use of a function value
still fails closed in `ks build` (KS4004).
"""
from __future__ import annotations

import shutil
import unittest

from tests import test_mir_go_native_v2_parity as _parity

GO = shutil.which("go")

CALLBACKS = """
fn positive(value: Int) -> Bool {
    return value > 0
}

fn double(value: Int) -> Int {
    return value * 2
}

fn long_name(name: String) -> Bool {
    return name.length() > 4
}

fn label(value: Int) -> String {
    return "#{value}"
}

fn main() {
    let scores = [3, -1, 2, 0, -7, 11]
    let empty: List<Int> = []
    println(scores.filter(positive))
    println(empty.filter(positive))
    println(scores.map(double))
    println(scores.map(label))
    println(scores.find(positive))
    println(empty.find(positive))
    println("{scores.any(positive)} {empty.any(positive)}")
    println(["ali", "mehmet", "ayşegül", "can"].filter(long_name))
    let kept = scores.filter(positive) or []
    println(kept.map(double))
}
"""

SORTS = """
fn main() {
    println([3, -1, 2, 0, -7, 11, 2].sort())
    println([2.5, -0.5, 1.0, 10.25].sort())
    println(["zeynep", "ali", "Çağla", "ayşe", "Zed", "", "ç"].sort())
    let empty: List<String> = []
    println(empty.sort())
    let nested = [[2], [1, 3]]
    println(nested.sort())
    let ordered = [5, 4, 3].sort() or []
    println(ordered.take(2))
}
"""


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeListCallbackTests(unittest.TestCase):
    # The three-way parity helpers, without re-running that file's tests.
    workspace = _parity.MirGoNativeParityTests.workspace
    ks_run = _parity.MirGoNativeParityTests.ks_run
    canonical_run = _parity.MirGoNativeParityTests.canonical_run
    native_run = _parity.MirGoNativeParityTests.native_run
    assert_parity = _parity.MirGoNativeParityTests.assert_parity

    def test_callbacks_match_both_executors(self) -> None:
        output = self.assert_parity(CALLBACKS)
        lines = output.splitlines()
        self.assertEqual(lines[0], "[3, 2, 11]")
        self.assertEqual(lines[1], "[]")
        self.assertEqual(lines[2], "[6, -2, 4, 0, -14, 22]")
        self.assertEqual(lines[4], "Some(3)")
        self.assertEqual(lines[5], "None")
        self.assertEqual(lines[6], "true false")
        self.assertEqual(lines[7], '["mehmet", "ayşegül"]')
        self.assertEqual(lines[8], "[6, 4, 22]")

    def test_sort_matches_both_executors(self) -> None:
        output = self.assert_parity(SORTS)
        lines = output.splitlines()
        self.assertEqual(lines[0], "[-7, -1, 0, 2, 2, 3, 11]")
        self.assertEqual(lines[1], "[-0.5, 1.0, 2.5, 10.25]")
        self.assertEqual(lines[2], '["", "Zed", "ali", "ayşe", "zeynep", "Çağla", "ç"]')
        self.assertEqual(lines[3], "[]")
        self.assertIn("yalnızca homojen String veya sayısal", lines[4])
        self.assertEqual(lines[5], "[3, 4]")

    def test_lambda_callback_matches_both_executors(self) -> None:
        # A lambda lowers to a named one-parameter function in MIR, so it
        # takes the same path as a named callback.
        output = self.assert_parity(
            "fn main() {\n    let xs = [1, 2, 3]\n"
            "    println(xs.filter(fn(x: Int) -> Bool { return x > 1 }))\n}\n"
        )
        self.assertEqual(output, "[2, 3]\n")


if __name__ == "__main__":
    unittest.main()
