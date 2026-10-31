"""Reconciled native launch: at-most-one local claim, no unsafe replay/rollback."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_pending_epoch_projection_v1 import PendingStrangeProjectionV1
from koschei.strange_pending_native_build_v1 import PendingStrangeNativeBuildV1
from koschei.strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchReconciliationError,
)
from koschei.strange_reconciled_native_launch_v1 import (
    StrangeReconciledNativeLaunchError,
    run_reconciled_activated_native_v1,
)
from koschei.strange_activated_candidate_launch_v1 import StrangeActivatedCandidateError
from koschei.strange_supervised_native_v1 import StrangeSupervisedRunV1

ROOT = Path(__file__).resolve().parents[1]


class StrangeReconciledNativeLaunchV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.temp.name) / "continuity.sqlite3", continuity_id="tenant-a",
        )
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        binary = b"local-test-binary-fixture"
        pending_projection = PendingStrangeProjectionV1(
            previous_epoch=4, target_epoch=5,
            starts_at_seconds=600, expires_before_seconds=720,
            source_sha256="c" * 64,
        )
        self.pending = PendingStrangeNativeBuildV1(
            binary=binary,
            pending_projection=pending_projection,
            native_sha256=hashlib.sha256(binary).hexdigest(),
            go_executable_sha256="d" * 64,
        )
        self.journal = StrangeEpochHandoffV1(self.store)
        self.now = 599
        self.stage = self.journal.stage(
            expected_old_epoch=4, expected_old_start_seconds=480,
            deployment_id="tenant-a/native",
            veyra_digest="a" * 64, mir_fingerprint=self.mir.fingerprint,
            source_sha256=pending_projection.source_sha256,
            native_binary=binary,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )
        self.reporting = StrangeDurableLaunchReconciliationV1(self.store)
        self.arguments = dict(
            continuity_store=self.store,
            pending=self.pending,
            handoff_key=b"H" * 32,
            expected_handoff_mac=self.stage.handoff_mac,
            trust_plane_seed=b"S" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/native",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256="d" * 64,
        )

    def activate(self):
        self.now = 600
        self.journal.activate(
            expected_old_epoch=4,
            expected_handoff_mac=self.stage.handoff_mac,
            handoff_key=b"H" * 32,
            seconds_reader=lambda: self.now,
        )

    def run(self, **changes):
        return run_reconciled_activated_native_v1(
            self.mir, **(self.arguments | changes)
        )

    def successful_native(self, exit_code=0):
        return StrangeSupervisedRunV1(
            exit_code=exit_code,
            observed_epoch=5,
            native_sha256=self.pending.native_sha256,
            stdout=b"OK" if exit_code == 0 else b"",
            stderr=b"" if exit_code == 0 else b"failed",
            checks=2,
        )

    def test_pre_activation_attempt_rejected_before_native_runner(self):
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1"
        ) as runner:
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
            runner.assert_not_called()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.reporting.read(epoch=5)

    def test_success_is_durably_reported_and_cannot_relaunch(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.successful_native(),
        ) as runner:
            result = self.run()
            self.assertFalse(result.authority)
            self.assertEqual(result.run.stdout, b"OK")
            self.assertEqual(result.report.state, "REPORTED_OK")
            self.assertFalse(result.report.authority)
            self.assertEqual(self.reporting.read(epoch=5).state, "REPORTED_OK")
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
            runner.assert_called_once()
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_failed_runner_reports_failure_but_never_restores_old_epoch(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=StrangeActivatedCandidateError("launch denied"),
        ) as runner:
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
            runner.assert_called_once()
        self.assertEqual(self.reporting.read(epoch=5).state, "REPORTED_FAILED")
        self.assertEqual(self.store.read_snapshot().epoch, 5)
        self.assertTrue(self.journal.retired(4))

    def test_nonzero_native_exit_is_reported_failed(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.successful_native(exit_code=7),
        ):
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
        self.assertEqual(self.reporting.read(epoch=5).state, "REPORTED_FAILED")

    def test_unknown_crash_leaves_claimed_no_automatic_rerun(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=KeyboardInterrupt("host interrupted"),
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.run()
        self.assertEqual(self.reporting.read(epoch=5).state, "CLAIMED")
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1"
        ) as runner:
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
            runner.assert_not_called()

    def test_expired_after_process_return_cannot_record_success(self):
        self.activate()
        def expire_before_report(*args, **kwargs):
            self.now = 720
            return self.successful_native()

        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=expire_before_report,
        ):
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
        self.assertEqual(self.reporting.read(epoch=5).state, "CLAIMED")

    def test_epoch_advance_after_process_return_cannot_record_success(self):
        self.activate()
        def rotate_before_report(*args, **kwargs):
            self.store.advance(
                expected_current_epoch=5, next_epoch=6,
                starts_at_seconds=720, observed_seconds=720,
            )
            self.now = 720
            return self.successful_native()

        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=rotate_before_report,
        ):
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
        self.assertEqual(self.reporting.read(epoch=5).state, "CLAIMED")
        self.assertEqual(self.store.read_snapshot().epoch, 6)

    def test_crashed_claim_blocks_relaunch_after_database_reopen(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=KeyboardInterrupt("interrupted after claim"),
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.run()
        with StrangeDurableContinuityV1(
            Path(self.temp.name) / "continuity.sqlite3",
            continuity_id="tenant-a",
        ) as second_store:
            with patch(
                "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1"
            ) as runner:
                with self.assertRaises(StrangeReconciledNativeLaunchError):
                    self.run(continuity_store=second_store)
                runner.assert_not_called()
            self.assertEqual(
                StrangeDurableLaunchReconciliationV1(second_store).read(epoch=5).state,
                "CLAIMED",
            )

    def test_failure_can_be_reported_after_current_window_expires(self):
        self.activate()

        def expire_and_fail(*args, **kwargs):
            self.now = 720
            raise StrangeActivatedCandidateError("epoch closed before exec")

        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=expire_and_fail,
        ):
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run()
        self.assertEqual(
            self.reporting.read(epoch=5).state,
            "REPORTED_FAILED",
        )
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_invalid_pending_candidate_does_not_consume_launch_claim(self):
        self.activate()
        corrupt = replace(self.pending, binary=b"wrong native bytes")
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1"
        ) as runner:
            with self.assertRaises(StrangeReconciledNativeLaunchError):
                self.run(pending=corrupt)
            runner.assert_not_called()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.reporting.read(epoch=5)

    def test_concurrent_requests_run_only_once_through_this_wrapper(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_launch_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.successful_native(),
        ) as runner:
            def attempt(_):
                try:
                    self.run()
                    return "ok"
                except StrangeReconciledNativeLaunchError:
                    return "denied"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(attempt, (0, 1)))
            self.assertEqual(sorted(results), ["denied", "ok"])
            runner.assert_called_once()
        self.assertEqual(self.reporting.read(epoch=5).state, "REPORTED_OK")


if __name__ == "__main__":
    unittest.main()
