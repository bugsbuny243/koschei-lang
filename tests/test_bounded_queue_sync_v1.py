from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from koschei.bounded_queue import BoundedQueueValue
from koschei.codegen_go import generate_go_mir
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.type_system import INT


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "examples" / "large_service" / "backpressure.ks"
GO_BINARY = shutil.which("go")


class BoundedQueuePythonSyncTests(unittest.TestCase):
    def test_queue_owns_one_lock_without_changing_capacity(self) -> None:
        queue = BoundedQueueValue(8, INT)
        self.assertIsInstance(queue._lock, type(threading.Lock()))
        self.assertEqual(len(queue._buffer), 8)
        self.assertEqual(queue.capacity, 8)

    def test_concurrent_producers_and_consumers_preserve_every_item_once(self) -> None:
        queue = BoundedQueueValue(32, INT)
        producer_count = 4
        consumer_count = 4
        per_producer = 250
        total = producer_count * per_producer
        start = threading.Barrier(producer_count + consumer_count)
        ticket_lock = threading.Lock()
        seen_lock = threading.Lock()
        next_ticket = 0
        seen: set[int] = set()
        failures: list[str] = []

        def producer(index: int) -> None:
            start.wait()
            base = index * per_producer
            for offset in range(per_producer):
                value = base + offset
                while not queue.try_send(value):
                    pass

        def consumer() -> None:
            nonlocal next_ticket
            start.wait()
            while True:
                with ticket_lock:
                    if next_ticket >= total:
                        return
                    next_ticket += 1
                while True:
                    ok, value = queue.try_recv()
                    if not ok:
                        continue
                    with seen_lock:
                        if value in seen:
                            failures.append(f"duplicate:{value}")
                        seen.add(value)
                    break

        threads = [
            threading.Thread(target=producer, args=(index,))
            for index in range(producer_count)
        ] + [threading.Thread(target=consumer) for _ in range(consumer_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(seen), total)
        self.assertEqual(seen, set(range(total)))
        self.assertEqual(queue.length, 0)
        self.assertEqual(len(queue._buffer), 32)


@unittest.skipUnless(GO_BINARY, "Go toolchain is required for race-detector proof")
class BoundedQueueGoRaceTests(unittest.TestCase):
    def test_shipping_generated_runtime_passes_go_race_detector(self) -> None:
        graph = load_graph(ENTRY)
        check_graph(graph)
        generated = generate_go_mir(require_mir(graph))

        self.assertIn('"sync"', generated)
        self.assertIn("Mu sync.Mutex", generated)
        self.assertIn("queue.Mu.Lock()", generated)
        self.assertIn("defer queue.Mu.Unlock()", generated)

        race_test = r'''package main

import (
    "runtime"
    "sync"
    "sync/atomic"
    "testing"
)

func TestKoscheiBoundedQueueConcurrentSendRecv(t *testing.T) {
    raw := ksBoundedQueue(int64(64), int64(0))
    queue, ok := raw.(*KsBoundedQueue)
    if !ok {
        t.Fatalf("bounded queue constructor returned %T", raw)
    }

    const producers = 4
    const consumers = 4
    const perProducer = 500
    const total = producers * perProducer

    start := make(chan struct{})
    var workers sync.WaitGroup
    var receiveTickets atomic.Int64
    var seenMu sync.Mutex
    seen := make(map[int64]struct{}, total)

    for producer := 0; producer < producers; producer++ {
        producer := producer
        workers.Add(1)
        go func() {
            defer workers.Done()
            <-start
            base := int64(producer * perProducer)
            for offset := 0; offset < perProducer; offset++ {
                value := base + int64(offset)
                for {
                    result := ksQueueTrySend(queue, value)
                    if sent, ok := result.(bool); ok {
                        if sent {
                            break
                        }
                        runtime.Gosched()
                        continue
                    }
                    t.Errorf("unexpected send result %T: %v", result, result)
                    return
                }
            }
        }()
    }

    for consumer := 0; consumer < consumers; consumer++ {
        workers.Add(1)
        go func() {
            defer workers.Done()
            <-start
            for {
                ticket := receiveTickets.Add(1) - 1
                if ticket >= int64(total) {
                    return
                }
                for {
                    result := ksQueueTryRecv(queue)
                    if value, ok := result.(int64); ok {
                        seenMu.Lock()
                        if _, duplicate := seen[value]; duplicate {
                            t.Errorf("duplicate queue item %d", value)
                        }
                        seen[value] = struct{}{}
                        seenMu.Unlock()
                        break
                    }
                    if _, empty := result.(*KsError); empty {
                        runtime.Gosched()
                        continue
                    }
                    t.Errorf("unexpected receive result %T: %v", result, result)
                    return
                }
            }
        }()
    }

    close(start)
    workers.Wait()

    seenMu.Lock()
    seenCount := len(seen)
    seenMu.Unlock()
    if seenCount != total {
        t.Fatalf("received %d unique items, want %d", seenCount, total)
    }
    remaining, ok := ksQueueLen(queue).(int64)
    if !ok || remaining != 0 {
        t.Fatalf("queue length = %v (%T), want int64(0)", remaining, remaining)
    }
}
'''

        with tempfile.TemporaryDirectory(prefix="koschei-queue-race-") as workspace:
            directory = Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "queue_race_test.go").write_text(race_test, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheiqueuerace\n\ngo 1.21\n", encoding="utf-8"
            )
            raced = subprocess.run(
                [GO_BINARY, "test", "-race", "-count=1", "."],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(raced.returncode, 0, raced.stdout + raced.stderr)
            self.assertNotIn("DATA RACE", raced.stdout + raced.stderr)


if __name__ == "__main__":
    unittest.main()
