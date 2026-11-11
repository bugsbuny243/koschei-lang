"""Orchestrator composition regressions; native launch mocked, SQLite real."""
from __future__ import annotations

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
from koschei.strange_cutover_orchestrator_v1 import (
    StrangeCutoverError,
    activate_and_reconcile_cutover_v1,
    prepare_and_stage_next_epoch_v1,
)

ROOT = Path(__file__).resolve().parents[1]


class StrangeCutoverOrchestratorV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        cls.mir = require_mir(graph)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.temp.name) / "continuity.sqlite3", continuity_id="tenant-a"
        )
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.now = 599
        binary = b"fake-native-fixture-not-executed"
        self.pending = PendingStrangeNativeBuildV1(
            binary=binary,
            pending_projection=PendingStrangeProjectionV1(
                previous_epoch=4, target_epoch=5, starts_at_seconds=600,
                expires_before_seconds=720, source_sha256="c" * 64,
            ),
            native_sha256=hashlib.sha256(binary).hexdigest(),
            go_executable_sha256="d" * 64,
        )
        self.prep = dict(
            continuity_store=self.store,
            trust_plane_seed=b"S" * 32,
            expected_current_epoch=4,
            expected_current_start_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            go_executable="/unused/pinned/go",
            expected_go_sha256="d" * 64,
            handoff_key=b"H" * 32,
        )

    def stage(self):
        with patch(
            "koschei.strange_cutover_orchestrator_v1.prebuild_next_strange_native_v1",
            return_value=self.pending,
        ) as build:
            staged = prepare_and_stage_next_epoch_v1(self.mir, **self.prep)
            build.assert_called_once()
            self.assertEqual(self.store.read_snapshot().epoch, 4)
            self.assertEqual(StrangeEpochHandoffV1(self.store).read(4).state, "STAGED")
            return staged

    def activate(self, staged, **overrides):
        args = dict(
            continuity_store=self.store,
            staged=staged,
            handoff_key=b"H" * 32,
            trust_plane_seed=b"S" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256="d" * 64,
        )
        args.update(overrides)
        return activate_and_reconcile_cutover_v1(self.mir, **args)

    def test_happy_path_stage_activate_retire_and_dispatch_once(self):
        staged = self.stage()
        self.now = 600
        outcome = object()
        with patch(
            "koschei.strange_cutover_orchestrator_v1.run_reconciled_prebuilt_strange_native_v1",
            return_value=outcome,
        ) as runner:
            self.assertIs(self.activate(staged), outcome)
            runner.assert_called_once()
            with self.assertRaises(StrangeCutoverError):
                self.activate(staged)
            runner.assert_called_once()
        self.assertEqual(self.store.read_snapshot().epoch, 5)
        self.assertTrue(StrangeEpochHandoffV1(self.store).retired(4))

    def test_replay_staging_is_denied(self):
        self.stage()
        with patch(
            "koschei.strange_cutover_orchestrator_v1.prebuild_next_strange_native_v1",
            return_value=self.pending,
        ):
            with self.assertRaises(StrangeCutoverError):
                prepare_and_stage_next_epoch_v1(self.mir, **self.prep)
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_tampered_hmac_in_durable_stage_is_rejected(self):
        staged = self.stage()
        with self.store._lock:
            self.store._db.execute(
                "UPDATE strange_handoffs_v1 SET handoff_mac=? "
                "WHERE continuity_id=? AND old_epoch=?",
                ("f" * 64, self.store.continuity_id, 4),
            )
        self.now = 600
        with patch(
            "koschei.strange_cutover_orchestrator_v1.run_reconciled_prebuilt_strange_native_v1"
        ) as runner:
            with self.assertRaises(StrangeCutoverError):
                self.activate(staged)
            runner.assert_not_called()
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_intra_transition_clock_rollback_denies_before_commit(self):
        staged = self.stage()
        readings = iter((600, 599))
        with patch(
            "koschei.strange_cutover_orchestrator_v1.run_reconciled_prebuilt_strange_native_v1"
        ) as runner:
            with self.assertRaises(StrangeCutoverError):
                self.activate(staged, seconds_reader=lambda: next(readings))
            runner.assert_not_called()
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_old_or_expired_window_and_corrupt_bytes_fail_closed(self):
        staged = self.stage()
        for seconds in (599, 720):
            self.now = seconds
            with self.assertRaises(StrangeCutoverError):
                self.activate(staged)
            self.assertEqual(self.store.read_snapshot().epoch, 4)
        self.now = 600
        corrupt = replace(staged.pending, binary=b"substituted")
        with self.assertRaises(StrangeCutoverError):
            self.activate(replace(staged, pending=corrupt))
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_failed_launch_does_not_undo_activated_epoch(self):
        staged = self.stage()
        self.now = 600
        with patch(
            "koschei.strange_cutover_orchestrator_v1.run_reconciled_prebuilt_strange_native_v1",
            side_effect=RuntimeError("unresolved launch"),
        ) as runner:
            with self.assertRaisesRegex(StrangeCutoverError, "do not replay"):
                self.activate(staged)
            runner.assert_called_once()
        self.assertEqual(self.store.read_snapshot().epoch, 5)
        self.assertTrue(StrangeEpochHandoffV1(self.store).retired(4))
        with self.assertRaises(StrangeCutoverError):
            self.activate(staged)


if __name__ == "__main__":
    unittest.main()
