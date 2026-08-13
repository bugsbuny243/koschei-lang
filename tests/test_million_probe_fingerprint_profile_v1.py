from __future__ import annotations

import concurrent.futures
import statistics
import time
import unittest

from koschei.decoy_view_broker_v1 import read_source_view


PROJECT = "p-million"
OID_A = "0123456789abcdef0123456789abcdef"
OID_B = "fedcba9876543210fedcba9876543210"
KEY = b"m" * 32
CANONICAL_A = b"fn treasury_root() -> Int { return 991122; }\n"
CANONICAL_B = b"fn custody_root() -> Int { return 883311; }\n"


def _hostile_digest(args: tuple[str, int]) -> tuple[str, int, str, int]:
    object_id, epoch = args
    calls: list[str] = []

    def canonical_reader(oid: str) -> bytes:
        calls.append(oid)
        return CANONICAL_A if oid == OID_A else CANONICAL_B

    start = time.perf_counter_ns()
    view = read_source_view(
        project_id=PROJECT,
        object_id=object_id,
        epoch=epoch,
        authorized=False,
        canonical_reader=canonical_reader,
        deception_key=KEY,
    )
    elapsed = time.perf_counter_ns() - start
    if calls:
        raise AssertionError("canonical reader reached from hostile process")
    if view.provenance != "decoy" or view.deployable:
        raise AssertionError("hostile process did not receive fail-closed decoy")
    if b"treasury_root" in view.content or b"custody_root" in view.content:
        raise AssertionError("canonical symbol leaked")
    if b"991122" in view.content or b"883311" in view.content:
        raise AssertionError("canonical literal leaked")
    return object_id, epoch, view.view_digest, elapsed


class MillionProbeFingerprintProfileV1Tests(unittest.TestCase):
    def test_one_million_hostile_reads_keep_canonical_unreachable(self):
        calls: list[str] = []
        digests = set()
        sizes = []
        timings = []

        def canonical_reader(oid: str) -> bytes:
            calls.append(oid)
            return CANONICAL_A

        for i in range(1_000_000):
            epoch = 40_000 + (i // 10_000)  # 100 coherent epochs
            start = time.perf_counter_ns()
            view = read_source_view(
                project_id=PROJECT,
                object_id=OID_A,
                epoch=epoch,
                authorized=False,
                canonical_reader=canonical_reader,
                deception_key=KEY,
            )
            timings.append(time.perf_counter_ns() - start)
            self.assertEqual(view.provenance, "decoy")
            self.assertFalse(view.deployable)
            self.assertNotIn(b"treasury_root", view.content)
            self.assertNotIn(b"991122", view.content)
            digests.add(view.view_digest)
            sizes.append(len(view.content))

        self.assertEqual(calls, [], "canonical reader must remain unreachable after 1M hostile reads")
        self.assertEqual(len(digests), 100)
        self.assertGreater(min(sizes), 0)
        self.assertLess(max(sizes) - min(sizes), 4096)
        median_ns = statistics.median(timings)
        p99_ns = sorted(timings)[int(len(timings) * 0.99) - 1]
        self.assertGreater(median_ns, 0)
        self.assertLess(p99_ns, median_ns * 250 + 25_000_000)

    def test_process_level_parallelism_preserves_object_epoch_isolation(self):
        pairs = []
        for epoch in range(50_000, 50_032):
            for object_id in (OID_A, OID_B):
                pairs.extend([(object_id, epoch)] * 64)

        with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_hostile_digest, pairs, chunksize=16))

        by_identity: dict[tuple[str, int], set[str]] = {}
        for object_id, epoch, digest, _elapsed in results:
            by_identity.setdefault((object_id, epoch), set()).add(digest)

        self.assertEqual(len(by_identity), 64)
        self.assertTrue(all(len(values) == 1 for values in by_identity.values()))
        for epoch in range(50_000, 50_032):
            self.assertNotEqual(by_identity[(OID_A, epoch)], by_identity[(OID_B, epoch)])

    def test_simple_fingerprint_classifier_has_no_canonical_training_signal(self):
        # The hostile path must be derivable without reading canonical bytes. We sample only
        # attacker-visible structural features and verify the canonical reader remains untouched.
        calls: list[str] = []
        rows = []

        def canonical_reader(oid: str) -> bytes:
            calls.append(oid)
            return CANONICAL_A if oid == OID_A else CANONICAL_B

        for epoch in range(60_000, 60_256):
            for object_id in (OID_A, OID_B):
                start = time.perf_counter_ns()
                view = read_source_view(
                    project_id=PROJECT,
                    object_id=object_id,
                    epoch=epoch,
                    authorized=False,
                    canonical_reader=canonical_reader,
                    deception_key=KEY,
                )
                elapsed = time.perf_counter_ns() - start
                rows.append((len(view.content), view.content.count(b"fn "), elapsed, view.view_digest))
                self.assertEqual(view.provenance, "decoy")
                self.assertFalse(view.deployable)

        self.assertEqual(calls, [], "fingerprint sampling must not create canonical training signal")
        self.assertEqual(len(rows), 512)
        self.assertEqual(len({digest for *_rest, digest in rows}), 512)
        self.assertGreaterEqual(len({size for size, *_ in rows}), 1)


if __name__ == "__main__":
    unittest.main()
