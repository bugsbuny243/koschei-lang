"""End-to-end local single-use launch claim, actual native run and failure reports."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
    StrangeLaunchReconciliationError,
)
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_pending_native_build_v1 import prebuild_next_strange_native_v1
from koschei.strange_reconciled_native_run_v1 import (
    StrangeReconciledNativeError,
    run_reconciled_prebuilt_strange_native_v1,
)
from koschei.strange_supervised_native_v1 import StrangeSupervisedRunV1

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
SUPPORTED = sys.platform == "linux" and GO is not None


@unittest.skipUnless(SUPPORTED, "real Linux + Go required for native launch")
class StrangeReconciledNativeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        cls.mir = require_mir(graph)
        go = str(Path(GO).resolve())
        with Path(go).open("rb") as fp:
            cls.go_pin = hashlib.file_digest(fp, "sha256").hexdigest()
        with StrangeDurableContinuityV1(
            Path(cls.tmp.name) / "builder.sqlite3", continuity_id="tenant-a",
        ) as continuity:
            continuity.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
            cls.pending = prebuild_next_strange_native_v1(
                cls.mir,
                continuity_store=continuity,
                trust_plane_seed=b"S" * 32,
                expected_current_epoch=4,
                expected_current_start_seconds=480,
                seconds_reader=lambda: 599,
                deployment_id="tenant-a/worker",
                veyra_digest="a" * 64,
                go_executable=go,
                expected_go_sha256=cls.go_pin,
            )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.temp.name) / "continuity.sqlite3", continuity_id="tenant-a",
        )
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.now = 599
        self.handoff = StrangeEpochHandoffV1(self.store)
        self.stage = self.handoff.stage(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            source_sha256=self.pending.pending_projection.source_sha256,
            native_binary=self.pending.binary,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )
        self.journal = StrangeDurableLaunchReconciliationV1(self.store)
        self.params = dict(
            continuity_store=self.store,
            pending=self.pending,
            handoff_key=b"H" * 32,
            expected_handoff_mac=self.stage.handoff_mac,
            trust_plane_seed=b"S" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256=self.go_pin,
            run_timeout_seconds=5,
            poll_interval_seconds=0.02,
        )

    def activate(self):
        self.now = 600
        self.handoff.activate(
            expected_old_epoch=4,
            expected_handoff_mac=self.stage.handoff_mac,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )

    def launch(self, **changes):
        return run_reconciled_prebuilt_strange_native_v1(self.mir, **(self.params | changes))

    def outcome(self):
        return self.journal.read(epoch=5)

    def test_pre_activation_rejected_without_creating_attempt(self):
        with self.assertRaises(StrangeReconciledNativeError):
            self.launch()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome()

    def test_real_native_run_reports_ok_exactly_once(self):
        self.activate()
        result = self.launch()
        self.assertFalse(result.authority)
        self.assertEqual(result.stdout, b"Koschei\n1\n")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.native_sha256, self.pending.native_sha256)
        self.assertEqual(self.outcome().state, "REPORTED_OK")
        self.assertFalse(self.outcome().authority)
        with self.assertRaises(StrangeReconciledNativeError):
            self.launch()

    def test_wrong_candidate_records_no_attempt(self):
        self.activate()
        with self.assertRaises(StrangeReconciledNativeError):
            self.launch(expected_handoff_mac="f" * 64)
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.outcome()
        self.assertEqual(self.launch().exit_code, 0)

    def test_runner_denial_is_recorded_and_no_auto_retry(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=ValueError("injected failed launch"),
        ):
            with self.assertRaises(StrangeReconciledNativeError):
                self.launch()
        self.assertEqual(self.outcome().state, "REPORTED_FAILED")
        with self.assertRaises(StrangeReconciledNativeError):
            self.launch()

    def test_nonzero_native_exit_is_reported_failed(self):
        self.activate()
        fake = StrangeSupervisedRunV1(
            exit_code=9,
            observed_epoch=5,
            native_sha256=self.pending.native_sha256,
            stdout=b"",
            stderr=b"not-ready",
        )
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            return_value=fake,
        ):
            with self.assertRaises(StrangeReconciledNativeError):
                self.launch()
        self.assertEqual(self.outcome().state, "REPORTED_FAILED")

    def test_expired_positive_outcome_remains_unresolved_not_success(self):
        self.activate()

        def run_then_expire(*args, **kwargs):
            self.now = 720
            return StrangeSupervisedRunV1(
                exit_code=0,
                observed_epoch=5,
                native_sha256=self.pending.native_sha256,
                stdout=b"Koschei\n1\n",
                stderr=b"",
            )

        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=run_then_expire,
        ):
            with self.assertRaisesRegex(StrangeReconciledNativeError, "unresolved"):
                self.launch()
        self.assertEqual(self.outcome().state, "CLAIMED")

    def test_crash_before_result_reporting_persists_claim(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_run_v1.StrangeDurableLaunchReconciliationV1.record_result",
            side_effect=StrangeLaunchReconciliationError("injected storage failure"),
        ):
            with self.assertRaisesRegex(StrangeReconciledNativeError, "unresolved"):
                self.launch()
        with StrangeDurableContinuityV1(
            Path(self.temp.name) / "continuity.sqlite3", continuity_id="tenant-a",
        ) as reopened:
            self.assertEqual(
                StrangeDurableLaunchReconciliationV1(reopened).read(epoch=5).state,
                "CLAIMED",
            )
        with self.assertRaises(StrangeReconciledNativeError):
            self.launch()

    def test_two_launchers_reserve_one_epoch_once(self):
        self.activate()
        def mock_runner(*args, **kwargs):
            return StrangeSupervisedRunV1(
                exit_code=0, observed_epoch=5, native_sha256=self.pending.native_sha256,
                stdout=b"", stderr=b"",
            )
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=mock_runner,
        ):
            def attempt(_):
                try:
                    self.launch()
                    return "reported"
                except StrangeReconciledNativeError:
                    return "rejected"
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sorted(outcomes), ["rejected", "reported"])
        self.assertEqual(self.outcome().state, "REPORTED_OK")


if __name__ == "__main__":
    unittest.main()
