"""Durable local launch attempt / outcome reconciliation regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchReconciliationError,
)

KEY = b"H" * 32


class StrangeLaunchReconciliationV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "continuity.sqlite3"
        self.store = StrangeDurableContinuityV1(self.db_path, continuity_id="tenant-a")
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.handoff = StrangeEpochHandoffV1(self.store)
        self.journal = StrangeDurableLaunchReconciliationV1(self.store)
        self.now = 599
        self.stage = self.handoff.stage(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            mir_fingerprint="b" * 64,
            source_sha256="c" * 64,
            native_binary=b"native-verified-elsewhere",
            seconds_reader=lambda: self.now,
            handoff_key=KEY,
        )

    def activate(self):
        self.now = 600
        self.handoff.activate(
            expected_old_epoch=4,
            expected_handoff_mac=self.stage.handoff_mac,
            seconds_reader=lambda: self.now,
            handoff_key=KEY,
        )

    def claim(self, **changes):
        args = dict(
            expected_epoch=5,
            expected_handoff_mac=self.stage.handoff_mac,
            expected_native_sha256=self.stage.native_sha256,
            handoff_key=KEY,
            seconds_reader=lambda: self.now,
        )
        args.update(changes)
        return self.journal.claim_once(**args)

    def outcome(self, success, **changes):
        args = dict(
            epoch=5,
            expected_handoff_mac=self.stage.handoff_mac,
            reported_success=success,
            seconds_reader=lambda: self.now,
            handoff_key=KEY,
        )
        args.update(changes)
        return self.journal.record_result(**args)

    def test_no_claim_before_activation_and_no_implicit_authority(self):
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.claim()
        self.assertEqual(self.store.read_snapshot().epoch, 4)
        self.activate()
        claim = self.claim()
        self.assertEqual((claim.epoch, claim.old_epoch, claim.state), (5, 4, "CLAIMED"))
        self.assertFalse(claim.authority)
        self.assertEqual(self.journal.read(epoch=5), claim)
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.claim()
        result = self.outcome(True)
        self.assertEqual((result.state, result.reported_seconds), ("REPORTED_OK", 600))
        self.assertFalse(result.authority)
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome(True)
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_claim_persists_after_restart_without_automatic_retry(self):
        self.activate()
        before = self.claim()
        with StrangeDurableContinuityV1(self.db_path, continuity_id="tenant-a") as second:
            fresh = StrangeDurableLaunchReconciliationV1(second)
            self.assertEqual(fresh.read(epoch=5), before)
            with self.assertRaises(StrangeLaunchReconciliationError):
                fresh.claim_once(
                    expected_epoch=5,
                    expected_handoff_mac=self.stage.handoff_mac,
                    expected_native_sha256=self.stage.native_sha256,
                    handoff_key=KEY,
                    seconds_reader=lambda: 600,
                )
            after = fresh.record_result(
                epoch=5,
                expected_handoff_mac=self.stage.handoff_mac,
                reported_success=False,
                seconds_reader=lambda: 601,
                handoff_key=KEY,
            )
            self.assertEqual(after.state, "REPORTED_FAILED")
            self.assertEqual(self.journal.read(epoch=5), after)

    def test_two_connections_can_claim_same_epoch_at_most_once(self):
        self.activate()
        with StrangeDurableContinuityV1(self.db_path, continuity_id="tenant-a") as second:
            other = StrangeDurableLaunchReconciliationV1(second)

            def attempt(journal):
                try:
                    journal.claim_once(
                        expected_epoch=5,
                        expected_handoff_mac=self.stage.handoff_mac,
                        expected_native_sha256=self.stage.native_sha256,
                        handoff_key=KEY,
                        seconds_reader=lambda: 600,
                    )
                    return "claimed"
                except StrangeLaunchReconciliationError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                verdict = list(executor.map(attempt, (self.journal, other)))
            self.assertEqual(sorted(verdict), ["claimed", "rejected"])

    def test_tampered_stage_key_and_candidate_fail_before_claim(self):
        self.activate()
        for bad in (
            {"expected_handoff_mac": "f" * 64},
            {"expected_native_sha256": "0" * 64},
            {"handoff_key": b"Z" * 32},
            {"expected_epoch": 4},
            {"expected_epoch": 6},
        ):
            with self.subTest(bad=bad), self.assertRaises(StrangeLaunchReconciliationError):
                self.claim(**bad)
        self.assertEqual(self.claim().state, "CLAIMED")

    def test_expired_window_and_advance_refuse_old_claim(self):
        self.activate()
        self.now = 720
        with self.assertRaises(ValueError):
            self.claim()
        self.store.advance(
            expected_current_epoch=5,
            next_epoch=6,
            starts_at_seconds=720,
            observed_seconds=720,
        )
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.claim()

    def test_late_success_cannot_be_reported_after_epoch_change(self):
        self.activate()
        self.claim()
        self.store.advance(
            expected_current_epoch=5,
            next_epoch=6,
            starts_at_seconds=720,
            observed_seconds=720,
        )
        self.now = 720
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome(True)
        self.assertEqual(self.journal.read(epoch=5).state, "CLAIMED")
        failed = self.outcome(False)
        self.assertEqual(failed.state, "REPORTED_FAILED")
        self.assertEqual(self.store.read_snapshot().epoch, 6)
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome(False)

    def test_clock_regression_and_invalid_reports_fail_closed(self):
        self.activate()
        self.now = 601
        self.claim()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome(False, seconds_reader=lambda: 600)
        for bad in (
            {"reported_success": 1},
            {"expected_handoff_mac": "BAD"},
            {"handoff_key": b"Z" * 32},
            {"seconds_reader": lambda: True},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.outcome(True, **bad)
        self.now = 602
        self.assertEqual(self.outcome(False).state, "REPORTED_FAILED")

    def test_tampered_stage_cannot_be_reported_as_success(self):
        self.activate()
        self.claim()
        self.store._db.execute(
            "UPDATE strange_handoffs_v1 SET source_sha256=? "
            "WHERE continuity_id=? AND old_epoch=?",
            ("0" * 64, "tenant-a", 4),
        )
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome(True)
        self.assertEqual(self.journal.read(epoch=5).state, "CLAIMED")

    def test_two_competing_reporters_cannot_both_commit_an_outcome(self):
        self.activate()
        self.claim()
        with StrangeDurableContinuityV1(self.db_path, continuity_id="tenant-a") as other_store:
            other = StrangeDurableLaunchReconciliationV1(other_store)

            def report(journal, outcome):
                try:
                    journal.record_result(
                        epoch=5,
                        expected_handoff_mac=self.stage.handoff_mac,
                        reported_success=outcome,
                        seconds_reader=lambda: 600,
                        handoff_key=KEY,
                    )
                    return "reported"
                except StrangeLaunchReconciliationError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(
                    lambda item: report(*item),
                    ((self.journal, True), (other, False)),
                ))
            self.assertEqual(sorted(results), ["rejected", "reported"])
            self.assertIn(self.journal.read(epoch=5).state, ("REPORTED_OK", "REPORTED_FAILED"))

    def test_claimed_record_survives_crash_without_roll_back(self):
        self.activate()
        self.claim()
        self.store.close()
        with StrangeDurableContinuityV1(self.db_path, continuity_id="tenant-a") as reopened:
            journal = StrangeDurableLaunchReconciliationV1(reopened)
            self.assertEqual(journal.read(epoch=5).state, "CLAIMED")
            self.assertEqual(reopened.read_snapshot().epoch, 5)
            with self.assertRaises(StrangeLaunchReconciliationError):
                journal.claim_once(
                    expected_epoch=5,
                    expected_handoff_mac=self.stage.handoff_mac,
                    expected_native_sha256=self.stage.native_sha256,
                    handoff_key=KEY,
                    seconds_reader=lambda: 600,
                )
        # This test deliberately closes self.store once before cleanup.


if __name__ == "__main__":
    unittest.main()
