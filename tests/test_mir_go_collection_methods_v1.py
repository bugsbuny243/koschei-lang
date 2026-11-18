"""Native List/Map methods agree with ks run and the canonical MIR.

sum/min/max, unique, flatten, chunks, first_difference, partition, scan and
Map.merge/add/keys_sorted_by_value: `ks build` refused every program that
called one of them (KS4004). Results, Result/Option shapes and error texts
must match the interpreter's (ergonomics_* modules and
runtime_primitive_facade_v1).
"""
from __future__ import annotations

import shutil
import unittest

from tests import test_mir_go_native_v2_parity as _parity

GO = shutil.which("go")

LISTS = """
fn positive(value: Int) -> Bool {
    return value > 0
}

fn running(total: Int, value: Int) -> Int {
    return total + value
}

fn longest(best: String, word: String) -> String {
    if word.length() > best.length() {
        return word
    }
    return best
}

fn main() {
    let numbers = [3, -1, 2, 0, -7, 11, 2]
    let empty: List<Int> = []
    println(numbers.sum())
    println(numbers.min())
    println(numbers.max())
    println(empty.sum())
    println([1.5, -0.25, 2.0].sum())
    println([1.5, -0.25, 2.0].min())
    println([9223372036854775807, 1].sum())
    println([1, 2].sum() or 0)
    println(numbers.unique())
    println(["a", "b", "a", "ç", "b"].unique())
    let groups = [[1, 2], [3]]
    println(groups.flatten())
    println(numbers.chunks(3))
    println(numbers.chunks(0))
    println(empty.chunks(2))
    println([1, 2, 3].first_difference([1, 2, 3]))
    println([1, 2, 3].first_difference([1, 9, 3]))
    println([1, 2].first_difference([1, 2, 3]))
    println(numbers.partition(positive))
    println(empty.partition(positive))
    println(numbers.scan(0, running))
    println(["ab", "c", "def", "gh"].scan("", longest))
    println(empty.scan(5, running))
}
"""

MAPS = """
fn main() {
    let left = {"a": 1, "b": 2}
    let right = {"b": 20, "c": 30}
    println(left.merge(right))
    println(right.merge(left))
    println(left.add("a", 5))
    println(left.add("z", 7))
    println({"x": 1.5}.add("x", 0.25))
    println(left.add("a", 9223372036854775807))
    let scores = {"zeynep": 3, "ali": 5, "can": 3, "ayşe": 9}
    println(scores.keys_sorted_by_value(false))
    println(scores.keys_sorted_by_value(true))
    println({"b": "elma", "a": "armut", "c": "elma"}.keys_sorted_by_value(false))
    let none: Map<String, Int> = {}
    println(none.keys_sorted_by_value(true))
}
"""


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeCollectionMethodTests(unittest.TestCase):
    workspace = _parity.MirGoNativeParityTests.workspace
    ks_run = _parity.MirGoNativeParityTests.ks_run
    canonical_run = _parity.MirGoNativeParityTests.canonical_run
    native_run = _parity.MirGoNativeParityTests.native_run
    assert_parity = _parity.MirGoNativeParityTests.assert_parity

    def test_list_methods_match_both_executors(self) -> None:
        lines = self.assert_parity(LISTS).splitlines()
        self.assertEqual(lines[0], "Ok(10)")
        self.assertEqual(lines[1], "Ok(-7)")
        self.assertEqual(lines[2], "Ok(11)")
        self.assertIn("boş List", lines[3])
        self.assertIn("KS3501", lines[6])
        self.assertEqual(lines[7], "3")
        self.assertEqual(lines[8], "[3, -1, 2, 0, -7, 11]")
        self.assertEqual(lines[10], "[1, 2, 3]")
        self.assertEqual(lines[11], "Ok([[3, -1, 2], [0, -7, 11], [2]])")
        self.assertIn("sıfırdan büyük", lines[12])
        self.assertEqual(lines[14], "None")
        self.assertEqual(lines[15], "Some(1)")
        self.assertEqual(lines[16], "Some(2)")
        self.assertEqual(lines[17], "[[3, 2, 11, 2], [-1, 0, -7]]")
        self.assertEqual(lines[19], "[3, 2, 4, 4, -3, 8, 10]")
        self.assertEqual(lines[20], '["ab", "ab", "def", "def"]')
        self.assertEqual(lines[21], "[]")

    def test_map_methods_match_both_executors(self) -> None:
        lines = self.assert_parity(MAPS).splitlines()
        self.assertEqual(lines[0], '{"a": 1, "b": 20, "c": 30}')
        self.assertEqual(lines[1], '{"b": 2, "c": 30, "a": 1}')
        self.assertEqual(lines[2], '{"a": 6, "b": 2}')
        self.assertEqual(lines[3], '{"a": 1, "b": 2, "z": 7}')
        self.assertIn("KS3501", lines[5])
        self.assertEqual(lines[6], '["can", "zeynep", "ali", "ayşe"]')
        self.assertEqual(lines[7], '["ayşe", "ali", "can", "zeynep"]')
        self.assertEqual(lines[8], '["a", "b", "c"]')
        self.assertEqual(lines[9], "[]")


if __name__ == "__main__":
    unittest.main()
