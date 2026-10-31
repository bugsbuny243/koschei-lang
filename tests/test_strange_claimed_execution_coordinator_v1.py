"""End-to-end local claim -> native worker -> authenticated report scenarios."""
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
from koschei.strange_claimed_execution_coordinator_v1 import (
    StrangeClaimedExecutionError,
    run_claimed_prebuilt_strange_native_v1,
)
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_durable_launch_reconciliation_v1 import StrangeDurableLaunchReconciliationV1
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_pending_epoch_projection_v1 import PendingStrangeProjectionV1
from koschei.strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    prebuild_next_strange_native_v1,
)
from koschei.strange_supervised_native_v1 import StrangeSupervisedRunV1

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")


class StrangeClaimedExecutionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
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
        self.now = 599
        self.binary = b"fake-worker-fixture"
        self.pending = PendingStrangeNativeBuildV1(
            binary=self.binary,
            pending_projection=PendingStrangeProjectionV1(
                previous_epoch=4, target_epoch=5, starts_at_seconds=600,
                expires_before_seconds=720, source_sha256="b" * 64,
            ),
            native_sha256=hashlib.sha256(self.binary).hexdigest(),
            go_executable_sha256="c" * 64,
        )
        self.handoff = StrangeEpochHandoffV1(self.store)
        self.journal = StrangeDurableLaunchReconciliationV1(self.store)
        self.stage = self.handoff.stage(
            expected_old_epoch=4, expected_old_start_seconds=480,
            deployment_id="tenant-a/worker", veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            source_sha256=self.pending.pending_projection.source_sha256,
            native_binary=self.pending.binary,
            seconds_reader=lambda: self.now, handoff_key=b"H" * 32,
        )
        self.args = dict(
            continuity_store=self.store,
            pending=self.pending,
            handoff_key=b"H" * 32,
            expected_handoff_mac=self.stage.handoff_mac,
            trust_plane_seed=b"K" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256="c" * 64,
        )

    def activate(self) -> None:
        self.now = 600
        self.handoff.activate(
            expected_old_epoch=4, expected_handoff_mac=self.stage.handoff_mac,
            seconds_reader=lambda: self.now, handoff_key=b"H" * 32,
        )

    def execute(self, **overrides):
        return run_claimed_prebuilt_strange_native_v1(
            self.mir, **(self.args | overrides),
        )

    def report(self, *, code: int = 0, epoch: int = 5, native_sha: str | None = None):
        return StrangeSupervisedRunV1(
            exit_code=code,
            observed_epoch=epoch,
            native_sha256=native_sha or hashlib.sha256(self.binary).hexdigest(),
            stdout=b"fixture",
            stderr=b"",
        )

    def test_claim_is_forbidden_before_activation(self):
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
        ) as run:
            with self.assertRaises(StrangeClaimedExecutionError):
                self.execute()
            run.assert_not_called()
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_successful_run_has_one_durable_non_authoritative_report(self):
        self.activate()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(),
        ) as worker:
            result, recorded = self.execute()
        worker.assert_called_once()
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(recorded.state, "REPORTED_OK")
        self.assertFalse(recorded.authority)
        self.assertEqual(self.journal.read(epoch=5), recorded)
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
        ) as again:
            with self.assertRaises(StrangeClaimedExecutionError):
                self.execute()
            again.assert_not_called()
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_runner_exception_records_failure_never_rollback_or_retry(self):
        self.activate()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=RuntimeError("cannot exec"),
        ):
            with self.assertRaisesRegex(StrangeClaimedExecutionError, "not rolled back"):
                self.execute()
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")
        self.assertEqual(self.store.read_snapshot().epoch, 5)
        with self.assertRaises(StrangeClaimedExecutionError):
            self.execute()

    def test_failed_process_or_fabricated_observation_is_not_success(self):
        self.activate()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(code=1),
        ):
            with self.assertRaises(StrangeClaimedExecutionError):
                self.execute()
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")

    def test_fake_success_with_wrong_epoch_is_reported_failed(self):
        self.activate()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(epoch=4),
        ):
            with self.assertRaises(StrangeClaimedExecutionError):
                self.execute()
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")

    def test_fake_success_with_wrong_native_hash_is_reported_failed(self):
        self.activate()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(native_sha="0" * 64),
        ):
            with self.assertRaises(StrangeClaimedExecutionError):
                self.execute()
        self.assertEqual(self.journal.read(epoch=5).state, "REPORTED_FAILED")

    def test_late_success_is_unresolved_not_rewritten_as_failed(self):
        self.activate()
        def complete_after_rotation(*args, **kwargs):
            self.store.advance(
                expected_current_epoch=5, next_epoch=6,
                starts_at_seconds=720, observed_seconds=720,
            )
            self.now = 720
            return self.report()

        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            side_effect=complete_after_rotation,
        ):
            with self.assertRaisesRegex(StrangeClaimedExecutionError, "unreconciled"):
                self.execute()
        self.assertEqual(self.journal.read(epoch=5).state, "CLAIMED")
        self.assertEqual(self.store.read_snapshot().epoch, 6)

    def test_wrong_key_candidate_and_clock_cannot_claim(self):
        self.activate()
        cases = (
            dict(expected_handoff_mac="0" * 64),
            dict(handoff_key=b"Z" * 32),
            dict(pending=self.pending.__class__(
                binary=b"changed",
                pending_projection=self.pending.pending_projection,
                native_sha256=hashlib.sha256(b"changed").hexdigest(),
                go_executable_sha256="c" * 64,
            )),
            dict(seconds_reader=lambda: True),
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), patch(
                "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            ) as spawn:
                with self.assertRaises(StrangeClaimedExecutionError):
                    self.execute(**kwargs)
                spawn.assert_not_called()
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(),
        ):
            self.execute()

    def test_concurrent_requests_never_launch_twice(self):
        self.activate()
        def attempt():
            try:
                self.execute()
                return "ok"
            except StrangeClaimedExecutionError:
                return "denied"
        with patch(
            "koschei.strange_claimed_execution_coordinator_v1.run_activated_prebuilt_strange_native_v1",
            return_value=self.report(),
        ) as worker:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: attempt(), (1, 2)))
        self.assertEqual(sorted(results), ["denied", "ok"])
        worker.assert_called_once()

    @unittest.skipUnless(
        sys.platform == "linux" and GO,
        "Linux and Go required for sealed-memfd native integration",
    )
    def test_real_prebuilt_go_native_is_claimed_and_reported(self):
        # Separate database rooted in the same current epoch, preparing real
        # canonical source and binary before stage/activation.
        with tempfile.TemporaryDirectory() as directory:
            with StrangeDurableContinuityV1(
                Path(directory) / "native.sqlite3", continuity_id="tenant-a",
            ) as store:
                store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
                go = str(Path(GO).resolve())
                with Path(go).open("rb") as f:
                    pin = hashlib.file_digest(f, "sha256").hexdigest()
                pending = prebuild_next_strange_native_v1(
                    self.mir,
                    continuity_store=store,
                    trust_plane_seed=b"K" * 32,
                    expected_current_epoch=4,
                    expected_current_start_seconds=480,
                    seconds_reader=lambda: 599,
                    deployment_id="tenant-a/worker",
                    veyra_digest="a" * 64,
                    go_executable=go,
                    expected_go_sha256=pin,
                )
                journal = StrangeEpochHandoffV1(store)
                stage = journal.stage(
                    expected_old_epoch=4, expected_old_start_seconds=480,
                    deployment_id="tenant-a/worker",
                    veyra_digest="a" * 64,
                    mir_fingerprint=self.mir.fingerprint,
                    source_sha256=pending.pending_projection.source_sha256,
                    native_binary=pending.binary,
                    seconds_reader=lambda: 599, handoff_key=b"H" * 32,
                )
                journal.activate(
                    expected_old_epoch=4,
                    expected_handoff_mac=stage.handoff_mac,
                    seconds_reader=lambda: 600, handoff_key=b"H" * 32,
                )
                outcome, recorded = run_claimed_prebuilt_strange_native_v1(
                    self.mir,
                    continuity_store=store,
                    pending=pending,
                    handoff_key=b"H" * 32,
                    expected_handoff_mac=stage.handoff_mac,
                    trust_plane_seed=b"K" * 32,
                    seconds_reader=lambda: 600,
                    deployment_id="tenant-a/worker",
                    veyra_digest="a" * 64,
                    attestation_key=b"A" * 32,
                    expected_go_sha256=pin,
                )
                self.assertEqual(outcome.exit_code, 0)
                self.assertEqual(outcome.stdout, b"Koschei\n1\n")
                self.assertEqual(recorded.state, "REPORTED_OK")
                self.assertFalse(recorded.authority)
