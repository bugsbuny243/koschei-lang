"""Generic structs in native binaries agree with ks run and the canonical MIR.

`ks build` refused every generic struct (KS4004). Instances now carry their
type arguments the way StructBuilderV1 records them, so type contracts,
printing, equality and field assignment behave as under `ks run`.
"""
from __future__ import annotations

import shutil
import unittest

from tests import test_mir_go_native_v2_parity as _parity

GO = shutil.which("go")

SOURCE = """
struct Box<T> {
    value: T,
    label: String,
}

struct Pair<A, B> {
    left: A,
    right: B,
}

struct Pending {}
struct Settled {}

stateful struct Settlement<S> starts Pending {
    id: Int,
    state: S,
}

pure transition fn settle(item: Settlement<Pending>) -> Settlement<Settled> {
    return Settlement { id: item.id, state: Settled {} }
}

pure fn settled_id(item: Settlement<Settled>) -> Int {
    return item.id
}

fn wrap<T>(item: T) -> Box<T> {
    return Box { value: item, label: "wrapped" }
}

fn unwrap<T>(box: Box<T>) -> T {
    return box.value
}

fn swap<A, B>(pair: Pair<A, B>) -> Pair<B, A> {
    return Pair { left: pair.right, right: pair.left }
}

fn relabel<T>(box: Box<T>, label: String) -> Box<T> {
    let mut copy = box
    copy.label = label
    return copy
}

fn main() {
    let mut number = Box { value: 1, label: "n" }
    number.value = 41 + 1
    println(number)
    println(unwrap(number))
    let text = wrap("ç")
    println(text)
    let nested = wrap(wrap([1, 2]))
    println(nested)
    println(unwrap(unwrap(nested)))
    let pair = Pair { left: 1, right: "bir" }
    println(swap(pair))
    println(swap(swap(pair)) == pair)
    println(relabel(text, "yeni"))
    println(wrap(1) == wrap(1))
    println(wrap(1) == wrap(2))
    let boxes = [wrap(3), wrap(4)]
    println(boxes)
    let maybe: Option<Box<Int>> = Some(wrap(5))
    println(maybe)
    let pending = Settlement { id: 42, state: Pending {} }
    println(settled_id(settle(pending)))
}
"""


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeGenericStructTests(unittest.TestCase):
    workspace = _parity.MirGoNativeParityTests.workspace
    ks_run = _parity.MirGoNativeParityTests.ks_run
    canonical_run = _parity.MirGoNativeParityTests.canonical_run
    native_run = _parity.MirGoNativeParityTests.native_run
    assert_parity = _parity.MirGoNativeParityTests.assert_parity

    def test_generic_structs_match_both_executors(self) -> None:
        lines = self.assert_parity(SOURCE).splitlines()
        self.assertEqual(lines[0], 'Box { value: 42, label: "n" }')
        self.assertEqual(lines[1], "42")
        # A struct built inside a generic function records "_" for a type
        # argument that is still a type variable (StructBuilderV1.finish), and
        # equality compares type arguments too: the round trip is not equal
        # to the original under ks run either.
        self.assertEqual(lines[6], "false")
        self.assertEqual(lines[8:10], ["true", "false"])
        self.assertEqual(lines[-1], "42")


if __name__ == "__main__":
    unittest.main()
