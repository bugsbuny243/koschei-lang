from __future__ import annotations

import concurrent.futures
import statistics
import time
import unittest

from koschei.decoy_view_broker_v1 import read_source_view


OID = "0123456789abcdef0123456789abcdef"
OTHER_OID = "fedcba9876543210fedcba9876543210"
KEY = b"h" * 32
CANONICAL = b"fn crown_jewel() -> Int { return 999999; }\n"


class HighVolumeAttackProfileV1Tests(unittest.TestCase):
    def _unauthorized_read(self, *, object_id: str, epoch: int, calls: list[str]):
        def canonical_reader(oid: str) -> bytes:
            calls.append(oid)
            return CANONICAL

        start = time.perf_counter_ns()
        view = read_source_view(
            project_id="p-high-volume",
            object_id=object_id,
            epoch=epoch,
            authorized=False,
            canonical_reader=canonical_reader,
            deception_key=KEY,
        )
        elapsed = time.perf_counter_ns() - start
        return view, elapsed

    def test_100k_unauthorized_probes_never_touch_canonical(self):
        calls: list[str] = []
        digests = set()
        sizes = []
        timings = []

        # Rotate through 100 epochs while issuing 1000 reads per epoch.
        for i in range(100_000):
            epoch = 10_000 + (i // 1000)
            view, elapsed = self._unauthorized_read(object_id=OID, epoch=epoch, calls=calls)
            self.assertEqual(view.provenance, "decoy")
            self.assertFalse(view.deployable)
            self.assertNotIn(b"crown_jewel", view.content)
            self.assertNotIn(b"999999", view.content)
            digests.add(view.view_digest)
            sizes.append(len(view.content))
            timings.append(elapsed)

        self.assertEqual(calls, [], "canonical reader must remain unreachable under 100k hostile probes")
        self.assertEqual(len(digests), 100, "100 tested epochs must produce 100 coherent decoy universes")
        self.assertGreater(min(sizes), 0)
        self.assertLess(max(sizes) - min(sizes), 4096, "response-size spread unexpectedly large")

        # Timing is observational in CI, not a constant-time claim. Guard only against catastrophic skew.
        median_ns = statistics.median(timings)
        p95_ns = sorted(timings)[int(len(timings) * 0.95) - 1]
        self.assertGreater(median_ns, 0)
        self.assertLess(p95_ns, median_ns * 100 + 10_000_000, "hostile-read timing distribution is catastrophically unstable")

    def test_concurrent_hostile_reads_stay_coherent_and_isolated(self):
        calls: list[str] = []

        def task(i: int):
            object_id = OID if i % 2 == 0 else OTHER_OID
            epoch = 20_000 + (i % 32)
            return object_id, epoch, self._unauthorized_read(object_id=object_id, epoch=epoch, calls=calls)[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(task, range(8192)))

        self.assertEqual(calls, [], "concurrent hostile reads must never touch canonical source")

        by_identity: dict[tuple[str, int], set[str]] = {}
        for object_id, epoch, view in results:
            self.assertEqual(view.provenance, "decoy")
            self.assertFalse(view.deployable)
            by_identity.setdefault((object_id, epoch), set()).add(view.view_digest)

        self.assertTrue(all(len(digests) == 1 for digests in by_identity.values()), "same object+epoch must remain coherent under concurrency")
        for epoch in range(20_000, 20_032):
            left = by_identity[(OID, epoch)]
            right = by_identity[(OTHER_OID, epoch)]
            self.assertNotEqual(left, right, "different objects must not collapse to same decoy fingerprint")

    def test_stale_dump_correlation_breaks_across_epoch_and_object(self):
        calls: list[str] = []
        stale, _ = self._unauthorized_read(object_id=OID, epoch=30_000, calls=calls)
        next_epoch, _ = self._unauthorized_read(object_id=OID, epoch=30_001, calls=calls)
        other_object, _ = self._unauthorized_read(object_id=OTHER_OID, epoch=30_000, calls=calls)

        self.assertEqual(calls, [])
        self.assertNotEqual(stale.view_digest, next_epoch.view_digest)
        self.assertNotEqual(stale.view_digest, other_object.view_digest)
        self.assertNotEqual(stale.content, next_epoch.content)
        self.assertNotEqual(stale.content, other_object.content)


if __name__ == "__main__":
    unittest.main()
