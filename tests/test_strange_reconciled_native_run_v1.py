"""Durable claim -> native runner -> result reconciliation contract tests."""
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
from koschei.strange_pending_epoch_projection_v1 import PendingStrangeProjectionV1
from koschei.strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    prebuild_next_strange_native_v1,
)
from koschei.strange_reconciled_native_run_v1 import (
    StrangeReconciledNativeRunError,
    run_reconciled_prebuilt_strange_native_v1,
)
from koschei.strange_supervised_native_v1 import StrangeSupervisedRunV1

ROOT = Path(__file__).resolve().parents[1]


class StrangeReconciledNativeRunV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "continuity.sqlite3"
        self.store = StrangeDurableContinuityV1(self.db, continuity_id="tenant-a")
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        self.now = 599
        binary = b"fixture-native-no-execution-capability"
        self.pending = PendingStrangeNativeBuildV1(
            binary=binary,
            native_sha256=hashlib.sha256(binary).hexdigest(),
            go_executable_sha256="1" * 64,
            pending_projection=PendingStrangeProjectionV1(
                previous_epoch=4,
                target_epoch=5,
                starts_at_seconds=600,
                expires_before_seconds=720,
                source_sha256="c" * 64,
            ),
        )
        self.handoff = StrangeEpochHandoffV1(self.store)
        self.stage = self.handoff.stage(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="tenant-a/native",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            source_sha256=self.pending.pending_projection.source_sha256,
            native_binary=binary,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )
        self.journal = StrangeDurableLaunchReconciliationV1(self.store)
        self.args = dict(
            continuity_store=self.store,
            pending=self.pending,
            handoff_key=b"H" * 32,
            expected_handoff_mac=self.stage.handoff_mac,
            trust_plane_seed=b"S" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/native",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256="1" * 64,
        )

    def activate(self):
        self.now = 600
        self.handoff.activate(
            expected_old_epoch=4,
            expected_handoff_mac=self.stage.handoff_mac,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )

    def observed(self, *, exit_code=0, epoch=5, native_sha=None):
        return StrangeSupervisedRunV1(
            exit_code=exit_code,
            observed_epoch=epoch,
            native_sha256=self.pending.native_sha256 if native_sha is None else native_sha,
            stdout=b"Koschei\n1\n",
            stderr=b"",
            checks=2,
        )

    def run_with_stub(self, result=None, **changes):
        if result is None:
            result = self.observed()
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            return_value=result,
        ) as launched:
            output = run_reconciled_prebuilt_strange_native_v1(
                self.mir, **(self.args | changes)
            )
        return output, launched.call_count

    def test_no_attempt_or_spawn_before_activated_handoff(self):
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
        ) as launched:
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
            launched.assert_not_called()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.journal.read(epoch=5)

    def test_bad_clock_rejected_before_claim_and_spawn(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
        ) as launched:
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(
                    self.mir, **(self.args | {"seconds_reader": None}),
                )
            launched.assert_not_called()
        with self.assertRaises(StrangeLaunchReconciliationError):
            self.journal.read(epoch=5)

    def test_one_success_and_no_second_execution_after_restart(self):
        self.activate()
        result, calls = self.run_with_stub()
        self.assertEqual(calls, 1)
        self.assertFalse(result.authority)
        self.assertEqual(result.launch_report.state, "REPORTED_OK")
        self.assertEqual(result.observation.stdout, b"Koschei\n1\n")
        with StrangeDurableContinuityV1(self.db, continuity_id="tenant-a") as reopened:
            self.assertEqual(
                StrangeDurableLaunchReconciliationV1(reopened).read(epoch=5).state,
                "REPORTED_OK",
            )
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
        ) as launched:
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
            launched.assert_not_called()

    def test_runner_exception_records_terminal_failed_without_epoch_rollback(self):
        self.activate()
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=OSError("worker cannot start"),
        ):
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_nonzero_worker_exit_reports_failure_and_does_not_retry(self):
        self.activate()
        with self.assertRaises(StrangeReconciledNativeRunError):
            self.run_with_stub(self.observed(exit_code=12))
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
        ) as launched:
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
            launched.assert_not_called()

    def test_wrong_worker_epoch_reports_failure(self):
        self.activate()
        with self.assertRaises(StrangeReconciledNativeRunError):
            self.run_with_stub(self.observed(epoch=4))
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")

    def test_wrong_worker_binary_digest_reports_failure(self):
        self.activate()
        with self.assertRaises(StrangeReconciledNativeRunError):
            self.run_with_stub(self.observed(native_sha="0" * 64))
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")

    def test_expired_success_report_leaves_unknown_claim(self):
        self.activate()
        def expire_while_running(*args, **kwargs):
            self.now = 720
            return self.observed()
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=expire_while_running,
        ):
            with self.assertRaises(StrangeReconciledNativeRunError):
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
        self.assertEqual(self.journal.read(epoch=5).state, "CLAIMED")
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_two_concurrent_launches_reserve_at_most_once(self):
        self.activate()
        def attempt(_):
            try:
                run_reconciled_prebuilt_strange_native_v1(self.mir, **self.args)
                return "ok"
            except StrangeReconciledNativeRunError:
                return "rejected"
        with patch(
            "koschei.strange_reconciled_native_run_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.observed(),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(attempt, (1, 2)))
        self.assertEqual(sorted(results), ["ok", "rejected"])
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_OK")


@unittest.skipUnless(sys.platform == "linux" and shutil.which("go"), "Linux/Go required")
class StrangeReconciledRealNativeV1Tests(unittest.TestCase):
    def test_real_next_epoch_go_binary_compiled_staged_activated_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "c.sqlite3"
            with StrangeDurableContinuityV1(path, continuity_id="tenant-a") as store:
                store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
                graph = load_graph(ROOT / "examples" / "hello.ks")
                check_graph(graph)
                mir = require_mir(graph)
                go = str(Path(shutil.which("go")).resolve())
                with Path(go).open("rb") as handle:
                    pin = hashlib.file_digest(handle, "sha256").hexdigest()
                now = {"v": 599}
                pending = prebuild_next_strange_native_v1(
                    mir, continuity_store=store, trust_plane_seed=b"S" * 32,
                    expected_current_epoch=4, expected_current_start_seconds=480,
                    seconds_reader=lambda: now["v"],
                    deployment_id="tenant-a/native", veyra_digest="a" * 64,
                    go_executable=go, expected_go_sha256=pin,
                )
                handoff = StrangeEpochHandoffV1(store)
                stage = handoff.stage(
                    expected_old_epoch=4, expected_old_start_seconds=480,
                    deployment_id="tenant-a/native", veyra_digest="a" * 64,
                    mir_fingerprint=mir.fingerprint,
                    source_sha256=pending.pending_projection.source_sha256,
                    native_binary=pending.binary, handoff_key=b"H" * 32,
                    seconds_reader=lambda: now["v"],
                )
                now["v"] = 600
                handoff.activate(
                    expected_old_epoch=4, expected_handoff_mac=stage.handoff_mac,
                    handoff_key=b"H" * 32, seconds_reader=lambda: now["v"],
                )
                output = run_reconciled_prebuilt_strange_native_v1(
                    mir, continuity_store=store, pending=pending,
                    handoff_key=b"H" * 32, expected_handoff_mac=stage.handoff_mac,
                    trust_plane_seed=b"S" * 32, seconds_reader=lambda: now["v"],
                    deployment_id="tenant-a/native", veyra_digest="a" * 64,
                    attestation_key=b"A" * 32, expected_go_sha256=pin,
                    run_timeout_seconds=5, poll_interval_seconds=0.02,
                )
                self.assertEqual(output.observation.exit_code, 0)
                self.assertEqual(output.observation.stdout, b"Koschei\n1\n")
                self.assertEqual(output.launch_report.state, "REPORTED_OK")
                self.assertFalse(output.authority)
                self.assertEqual(
                    StrangeDurableLaunchReconciliationV1(store).read(epoch=5).state,
                    "REPORTED_OK",
                )


if __name__ == "__main__":
    unittest.main()
