"""Crash, restart, clock-window and concurrent-writer regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
)
from koschei.strange_representation_epoch_v1 import (
    StrangeRepresentationEpochError,
    require_strange_epoch_window_v1,
)


class StrangeDurableContinuityV1Tests(unittest.TestCase):
    def test_restart_keeps_epoch_and_prevents_reinitialization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "continuity.sqlite3"
            with StrangeDurableContinuityV1(path, continuity_id="tenant-a") as store:
                first = store.initialize(epoch=7, starts_at_seconds=840, observed_seconds=841)
                self.assertEqual((first.epoch, first.expires_before_seconds), (7, 960))
            with StrangeDurableContinuityV1(path, continuity_id="tenant-a") as store:
                self.assertEqual(store.read_snapshot(), first)
                with self.assertRaises(StrangeDurableContinuityError):
                    store.initialize(epoch=7, starts_at_seconds=840, observed_seconds=841)
                self.assertEqual(store.read_snapshot(), first)

    def test_transition_is_fenced_by_current_epoch_and_exact_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(Path(directory)/"s.db", continuity_id="a") as store:
                store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=485)
                with self.assertRaises(StrangeDurableContinuityError):
                    store.advance(expected_current_epoch=4, next_epoch=5, starts_at_seconds=599, observed_seconds=599)
                with self.assertRaises(StrangeDurableContinuityError):
                    store.advance(expected_current_epoch=4, next_epoch=5, starts_at_seconds=600, observed_seconds=599)
                result = store.advance(expected_current_epoch=4, next_epoch=5, starts_at_seconds=600, observed_seconds=600)
                self.assertEqual(result.epoch, 5)
                with self.assertRaises(StrangeDurableContinuityError):
                    store.advance(expected_current_epoch=4, next_epoch=6, starts_at_seconds=720, observed_seconds=720)
                self.assertEqual(store.read_snapshot().epoch, 5)

    def test_skip_elapsed_epochs_but_never_roll_back(self):
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(Path(directory)/"s.db", continuity_id="a") as store:
                store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
                result = store.advance(expected_current_epoch=4, next_epoch=7, starts_at_seconds=840, observed_seconds=858)
                self.assertEqual((result.epoch, result.starts_at_seconds), (7, 840))
                with self.assertRaises(StrangeDurableContinuityError):
                    store.advance(expected_current_epoch=7, next_epoch=6, starts_at_seconds=720, observed_seconds=720)

    def test_writer_returns_its_exact_committed_epoch_without_postcommit_reread(self):
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(Path(directory)/"s.db", continuity_id="a") as store:
                with patch.object(store, "read_snapshot", side_effect=AssertionError("post-commit reread forbidden")):
                    first = store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
                    second = store.advance(expected_current_epoch=4, next_epoch=5, starts_at_seconds=600, observed_seconds=600)
                self.assertEqual(first.epoch, 4)
                self.assertEqual(second.epoch, 5)
                self.assertEqual(store.read_snapshot().epoch, 5)

    def test_two_connections_cannot_commit_same_expected_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"s.db"
            with StrangeDurableContinuityV1(path, continuity_id="a") as first:
                first.initialize(epoch=1, starts_at_seconds=120, observed_seconds=120)
                with StrangeDurableContinuityV1(path, continuity_id="a") as second:
                    def attempt(store):
                        try:
                            store.advance(expected_current_epoch=1, next_epoch=2, starts_at_seconds=240, observed_seconds=240)
                            return "committed"
                        except StrangeDurableContinuityError:
                            return "rejected"
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        results = list(executor.map(attempt, (first, second)))
                    self.assertEqual(sorted(results), ["committed", "rejected"])
                    self.assertEqual(first.read_snapshot().epoch, 2)
                    self.assertEqual(second.read_snapshot().epoch, 2)

    def test_continuity_binding_rejects_stale_epoch_in_strange_build_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(Path(directory)/"s.db", continuity_id="a") as store:
                store.initialize(epoch=2, starts_at_seconds=240, observed_seconds=241)
                authority = store.as_continuity_authority()
                self.assertFalse(authority.authority)
                self.assertEqual(
                    require_strange_epoch_window_v1(
                        continuity=authority, expected_epoch=2,
                        starts_at_seconds=240, seconds_reader=lambda: 359,
                    ), 359,
                )
                store.advance(expected_current_epoch=2, next_epoch=3, starts_at_seconds=360, observed_seconds=360)
                with self.assertRaises(StrangeRepresentationEpochError):
                    require_strange_epoch_window_v1(
                        continuity=authority, expected_epoch=2,
                        starts_at_seconds=240, seconds_reader=lambda: 359,
                    )
                self.assertEqual(
                    require_strange_epoch_window_v1(
                        continuity=authority, expected_epoch=3,
                        starts_at_seconds=360, seconds_reader=lambda: 360,
                    ), 360,
                )

    def test_missing_and_bad_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(Path(directory)/"s.db", continuity_id="a") as store:
                with self.assertRaises(StrangeDurableContinuityError):
                    store.read_snapshot()
                for epoch, start, observed in ((True, 120, 120), (1, -1, 0), (1, 120, 240), (1, 2**63-1, 2**63-1)):
                    with self.subTest(epoch=epoch, start=start), self.assertRaises(StrangeDurableContinuityError):
                        store.initialize(epoch=epoch, starts_at_seconds=start, observed_seconds=observed)


if __name__ == "__main__":
    unittest.main()
