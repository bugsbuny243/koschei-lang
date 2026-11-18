"""Bounded queues, task scopes and parallel_map in native binaries.

`ks build` refused every program using them (KS4004). Task scopes are
cooperative: spawn records work and task_join_all runs the non-cancelled
tasks in spawn order, so a binary must print exactly what `ks run` and the
canonical MIR print, every KS39xx error included.
"""
from __future__ import annotations

import shutil
import unittest

from tests import test_mir_go_native_v2_parity as _parity

GO = shutil.which("go")

QUEUES = """
fn main() {
    let queue = bounded_queue(2, 0) or return
    println(queue)
    println(queue_try_send(queue, 1))
    println(queue_try_send(queue, 2))
    println(queue_try_send(queue, 3))
    println(queue)
    println(queue_len(queue))
    println(queue_capacity(queue))
    println(queue_try_recv(queue) or -1)
    println(queue_try_send(queue, 4))
    println(queue_try_recv(queue) or -1)
    println(queue_try_recv(queue) or -1)
    println(queue_try_recv(queue) or -1)
    let words = bounded_queue(1, "") or return
    println(queue_try_send(words, "ç"))
    println(queue_try_recv(words) or "none")
    let none = bounded_queue(0, 0) or {
        println("capacity refused")
        return
    }
}
"""

TASKS = """
fn push(queue: BoundedQueue<Int>) {
    queue_try_send(queue, queue_len(queue) + 10)
}

fn double(value: Int) -> Int {
    return value * 2
}

fn label(value: Int) -> String {
    return "#{value}"
}

fn broken(value: Int) -> Int or Error {
    if value == 3 {
        return Error("three")
    }
    return value
}

fn main() {
    let queue = bounded_queue(4, 0) or return
    let scope = task_scope(3) or return
    println(scope)
    let a = task_spawn(scope, push, queue) or -1
    let b = task_spawn(scope, push, queue) or -1
    let c = task_spawn(scope, push, queue) or -1
    let d = task_spawn(scope, push, queue) or -1
    println("{a} {b} {c} {d}")
    println(task_cancel(scope, b) or false)
    println(task_cancel(scope, b) or false)
    println(task_cancel(scope, 9) or false)
    println(task_pending(scope))
    println(task_capacity(scope))
    task_join_all(scope) or return
    println(scope)
    println(task_closed(scope))
    println(task_pending(scope))
    println(task_spawn(scope, push, queue) or -1)
    println(task_cancel(scope, a) or false)
    println(task_cancel_all(scope) or -1)
    println(queue_try_recv(queue) or -1)
    println(queue_try_recv(queue) or -1)
    println(queue_try_recv(queue) or -1)

    let cancelled = task_scope(2) or return
    let x = task_spawn(cancelled, push, queue) or -1
    let y = task_spawn(cancelled, push, queue) or -1
    println(task_cancel_all(cancelled) or -1)
    println(task_cancel_all(cancelled) or -1)
    task_join_all(cancelled) or return
    task_join_all(cancelled) or return
    println(cancelled)
    println(queue_len(queue))
    let refused = task_scope(5000) or {
        println("scope refused")
        return
    }
}
"""

PARALLEL = """
fn double(value: Int) -> Int {
    return value * 2
}

fn label(value: Int) -> String {
    return "#{value}"
}

fn main() {
    let values = [1, 2, 3, 4]
    println(parallel_map(values, double, 2) or [])
    println(parallel_map(values, label, 64) or [])
    let empty: List<Int> = []
    println(parallel_map(empty, double, 1) or [0])
    let limit = 60 + 5
    println(parallel_map(values, double, limit) or [0])
    let words = ["a", "b"]
    println(parallel_map(values, double, 1) or [])
}
"""


@unittest.skipUnless(GO, "Go toolchain unavailable")
class NativeTaskTests(unittest.TestCase):
    workspace = _parity.MirGoNativeParityTests.workspace
    ks_run = _parity.MirGoNativeParityTests.ks_run
    canonical_run = _parity.MirGoNativeParityTests.canonical_run
    native_run = _parity.MirGoNativeParityTests.native_run
    assert_parity = _parity.MirGoNativeParityTests.assert_parity

    def test_queues_match_both_executors(self) -> None:
        lines = self.assert_parity(QUEUES).splitlines()
        self.assertEqual(lines[0], "BoundedQueue(len=0, capacity=2)")
        self.assertEqual(lines[1:4], ["true", "true", "false"])
        self.assertEqual(lines[-1], "capacity refused")

    def test_task_scopes_match_both_executors(self) -> None:
        lines = self.assert_parity(TASKS).splitlines()
        self.assertEqual(lines[0], "TaskScope(tasks=0, pending=0, capacity=3, closed=false)")
        self.assertEqual(lines[1], "0 1 2 -1")
        self.assertEqual(lines[-1], "scope refused")

    def test_parallel_map_matches_both_executors(self) -> None:
        lines = self.assert_parity(PARALLEL).splitlines()
        self.assertEqual(lines[0], "[2, 4, 6, 8]")
        self.assertEqual(lines[3], "[0]")


if __name__ == "__main__":
    unittest.main()
