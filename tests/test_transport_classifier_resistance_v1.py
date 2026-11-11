from __future__ import annotations

import unittest

from koschei.read_transport_shaping_v1 import read_shaped_source


OID = "0123456789abcdef0123456789abcdef"
DECEPTION_KEY = b"d" * 32
SHAPING_KEY = b"s" * 32
BUCKET = 2048
FLOOR_NS = 5_000_000


class DeterministicClock:
    """Clock/sleeper pair that models an exact externally visible floor."""

    def __init__(self):
        self.now = 0

    def clock_ns(self) -> int:
        return self.now

    def sleeper(self, seconds: float) -> None:
        self.now += int(round(seconds * 1_000_000_000))


def _accuracy(labels: list[int], guesses: list[int]) -> float:
    return sum(int(a == b) for a, b in zip(labels, guesses)) / len(labels)


def _best_single_threshold(values: list[int], labels: list[int]) -> float:
    """Best training-set threshold accuracy, including both orientations."""
    candidates = sorted(set(values))
    if not candidates:
        return 0.5
    thresholds = [candidates[0] - 1, *candidates, candidates[-1] + 1]
    best = 0.0
    for threshold in thresholds:
        for invert in (False, True):
            guesses = []
            for value in values:
                guess = int(value > threshold)
                if invert:
                    guess = 1 - guess
                guesses.append(guess)
            best = max(best, _accuracy(labels, guesses))
    return best


class TransportClassifierResistanceV1Tests(unittest.TestCase):
    def _sample(self, *, authorized: bool, epoch: int, canonical: bytes):
        clock = DeterministicClock()
        response = read_shaped_source(
            project_id="p-classifier",
            object_id=OID,
            epoch=epoch,
            authorized=authorized,
            canonical_reader=lambda _: canonical,
            deception_key=DECEPTION_KEY,
            shaping_key=SHAPING_KEY,
            bucket_bytes=BUCKET,
            target_floor_ns=FLOOR_NS,
            clock_ns=clock.clock_ns,
            sleeper=clock.sleeper,
        )
        # Only externally observable transport metadata is returned to the
        # simulated classifier. provenance/payload_length are deliberately not.
        return len(response.transport), response.elapsed_ns

    def test_fixed_bucket_and_floor_reduce_metadata_classifier_to_chance(self):
        labels: list[int] = []
        sizes: list[int] = []
        elapsed: list[int] = []

        # Balanced corpus. Canonical source length intentionally varies so an
        # unshaped length classifier would have a useful signal.
        for i in range(1000):
            authorized = (i % 2) == 0
            canonical = (
                b"fn canonical_" + str(i).encode("ascii") + b"() -> Int { return 1; }\n"
                + (b"// canonical-padding\n" * (i % 17))
            )
            size, took = self._sample(authorized=authorized, epoch=50_000 + i, canonical=canonical)
            labels.append(1 if authorized else 0)
            sizes.append(size)
            elapsed.append(took)

        self.assertEqual(set(sizes), {BUCKET})
        self.assertEqual(set(elapsed), {FLOOR_NS})
        self.assertLessEqual(_best_single_threshold(sizes, labels), 0.50)
        self.assertLessEqual(_best_single_threshold(elapsed, labels), 0.50)

    def test_negative_control_unshaped_payload_length_is_classifiable(self):
        labels: list[int] = []
        raw_lengths: list[int] = []

        # Deliberately separated raw length distributions demonstrate that the
        # classifier harness can detect a trivial side channel when present.
        for i in range(1000):
            authorized = (i % 2) == 0
            labels.append(1 if authorized else 0)
            if authorized:
                raw_lengths.append(900 + (i % 31))
            else:
                raw_lengths.append(180 + (i % 23))

        self.assertGreaterEqual(_best_single_threshold(raw_lengths, labels), 0.99)

    def test_classifier_surface_excludes_internal_provenance_and_payload_length(self):
        canonical = b"fn secret_business_logic() -> Int { return 42; }\n"
        canonical_obs = self._sample(authorized=True, epoch=70_001, canonical=canonical)
        decoy_obs = self._sample(authorized=False, epoch=70_002, canonical=canonical)
        self.assertEqual(len(canonical_obs), 2)
        self.assertEqual(len(decoy_obs), 2)
        self.assertEqual(canonical_obs, decoy_obs)


if __name__ == "__main__":
    unittest.main()
