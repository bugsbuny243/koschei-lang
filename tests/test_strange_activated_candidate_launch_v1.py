"""Actual Go prebuild -> staged epoch -> active sealed worker integration tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_native_admission_v1 import issue_strange_native_attestation_v1
from koschei.strange_representation_epoch_v1 import project_strange_epoch_go_v1
from koschei.strange_supervised_native_v1 import (
    StrangeSupervisedNativeError,
    run_strange_supervised_native_v1,
)
from koschei.strange_pending_native_build_v1 import prebuild_next_strange_native_v1
from koschei.strange_activated_candidate_launch_v1 import (
    StrangeActivatedCandidateError,
    run_activated_prebuilt_strange_native_v1,
)

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
SUPPORTED = sys.platform == "linux" and GO is not None


@unittest.skipUnless(SUPPORTED, "Linux and Go required for real prebuild->launch")
class StrangeActivatedCandidateV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        cls.mir = require_mir(graph)
        cls.go = str(Path(GO).resolve())
        with Path(cls.go).open("rb") as stream:
            cls.go_pin = hashlib.file_digest(stream, "sha256").hexdigest()
        with StrangeDurableContinuityV1(
            Path(cls.root.name) / "prebuild.sqlite3", continuity_id="galaxy-a",
        ) as store:
            store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
            cls.pending = prebuild_next_strange_native_v1(
                cls.mir,
                continuity_store=store,
                trust_plane_seed=b"S" * 32,
                expected_current_epoch=4,
                expected_current_start_seconds=480,
                seconds_reader=lambda: 599,
                deployment_id="galaxy-a/native",
                veyra_digest="a" * 64,
                go_executable=cls.go,
                expected_go_sha256=cls.go_pin,
            )
        # A deliberately sleeping *test fixture* worker for verifying the
        # old process group's retirement. It is not claimed to be a
        # canonical MIR-produced executable or source->binary build proof.
        root = Path(cls.root.name)
        (root / "sleep.go").write_text(
            'package main\nimport "time"\nfunc main() { time.Sleep(3 * time.Second) }\n',
            encoding="utf-8",
        )
        old_exe = root / "sleep-native"
        built = subprocess.run(
            [cls.go, "build", "-trimpath", "-buildvcs=false",
             "-ldflags=-buildid=", "-o", str(old_exe), str(root / "sleep.go")],
            capture_output=True, text=True, timeout=90, check=False,
        )
        if built.returncode:
            raise AssertionError(built.stderr)
        cls.sleep_binary = old_exe.read_bytes()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.work.name) / "continuity.sqlite3", continuity_id="galaxy-a",
        )
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.journal = StrangeEpochHandoffV1(self.store)
        self.now = 599
        self.stage = self.journal.stage(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            source_sha256=self.pending.pending_projection.source_sha256,
            native_binary=self.pending.binary,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )
        self.args = dict(
            continuity_store=self.store,
            pending=self.pending,
            handoff_key=b"H" * 32,
            expected_handoff_mac=self.stage.handoff_mac,
            trust_plane_seed=b"S" * 32,
            seconds_reader=lambda: self.now,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
            attestation_key=b"A" * 32,
            expected_go_sha256=self.go_pin,
            run_timeout_seconds=5,
            poll_interval_seconds=0.02,
        )

    def launch(self, **changes):
        return run_activated_prebuilt_strange_native_v1(
            self.mir, **(self.args | changes)
        )

    def activate(self):
        self.now = 600
        self.journal.activate(
            expected_old_epoch=4,
            expected_handoff_mac=self.stage.handoff_mac,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )

    def test_future_native_is_never_executed_before_activation(self):
        with patch(
            "koschei.strange_activated_candidate_launch_v1.run_strange_supervised_native_v1",
            side_effect=AssertionError("pre-activation spawn forbidden"),
        ) as launched:
            with self.assertRaises(StrangeActivatedCandidateError):
                self.launch()
            launched.assert_not_called()
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_real_precompiled_go_executable_runs_after_epoch_transition(self):
        self.activate()
        result = self.launch()
        self.assertFalse(result.authority)
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(result.stdout, b"Koschei\n1\n")
        self.assertEqual(result.observed_epoch, 5)
        self.assertEqual(result.native_sha256, self.pending.native_sha256)
        self.assertTrue(self.journal.retired(4))

    def test_old_supervised_worker_is_stopped_and_new_prebuilt_worker_runs(self):
        _old_source, old_receipt = project_strange_epoch_go_v1(
            self.mir,
            trust_plane_seed=b"S" * 32,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
        )
        old_proof = issue_strange_native_attestation_v1(
            receipt=old_receipt, native_binary=self.sleep_binary,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4, starts_at_seconds=480,
            seconds_reader=lambda: self.now, attestation_key=b"A" * 32,
        )
        def run_old_worker():
            return run_strange_supervised_native_v1(
                continuity_store=self.store,
                attestation=old_proof,
                native_binary=self.sleep_binary,
                expected_source_sha256=old_receipt.source_sha256,
                deployment_id="galaxy-a/native",
                veyra_digest="a" * 64,
                mir_fingerprint=self.mir.fingerprint,
                expected_epoch=4, expected_start_seconds=480,
                seconds_reader=lambda: self.now,
                attestation_key=b"A" * 32,
                run_timeout_seconds=5, poll_interval_seconds=0.02,
            )

        started = Event()
        native_popen = subprocess.Popen

        def record_old_spawn(*args, **kwargs):
            worker = native_popen(*args, **kwargs)
            started.set()
            return worker

        with patch(
            "koschei.strange_supervised_native_v1.subprocess.Popen",
            side_effect=record_old_spawn,
        ):
            with ThreadPoolExecutor(max_workers=1) as pool:
                old_future = pool.submit(run_old_worker)
                self.assertTrue(started.wait(timeout=3), "old worker never spawned")
                self.activate()
                with self.assertRaises(StrangeSupervisedNativeError):
                    old_future.result(timeout=5)
        new_result = self.launch()
        self.assertEqual(new_result.stdout, b"Koschei\n1\n")
        self.assertEqual(new_result.observed_epoch, 5)
        self.assertFalse(new_result.authority)

    def test_stage_and_candidate_tampering_fail_closed(self):
        self.activate()
        cases = (
            dict(pending=replace(self.pending, binary=self.pending.binary + b"tamper")),
            dict(pending=replace(self.pending, native_sha256="f" * 64)),
            dict(
                pending=replace(
                    self.pending,
                    pending_projection=replace(
                        self.pending.pending_projection, source_sha256="f" * 64,
                    ),
                ),
            ),
            dict(expected_go_sha256="0" * 64),
            dict(expected_handoff_mac="f" * 64),
            dict(handoff_key=b"J" * 32),
            dict(deployment_id="another-tenant/native"),
            dict(veyra_digest="b" * 64),
            dict(trust_plane_seed=b"Z" * 32),
        )
        for mismatch in cases:
            with self.subTest(change=list(mismatch)), self.assertRaises(StrangeActivatedCandidateError):
                self.launch(**mismatch)

    def test_activated_stage_corruption_fails_before_spawn(self):
        self.activate()
        self.store._db.execute(
            "UPDATE strange_handoffs_v1 SET native_sha256=? "
            "WHERE continuity_id=? AND old_epoch=?",
            ("f" * 64, "galaxy-a", 4),
        )
        with patch(
            "koschei.strange_activated_candidate_launch_v1.run_strange_supervised_native_v1",
        ) as launched:
            with self.assertRaises(StrangeActivatedCandidateError):
                self.launch()
            launched.assert_not_called()

    def test_expired_activated_window_rejected(self):
        self.activate()
        self.now = 720
        with self.assertRaises(StrangeActivatedCandidateError):
            self.launch()

    def test_revoked_epoch_before_launch_rejected(self):
        self.activate()
        self.store.advance(
            expected_current_epoch=5,
            next_epoch=6,
            starts_at_seconds=720,
            observed_seconds=720,
        )
        self.now = 720
        with self.assertRaises(StrangeActivatedCandidateError):
            self.launch()

    def test_epoch_rotation_between_issue_and_spawn_fails_closed(self):
        self.activate()
        from koschei.strange_activated_candidate_launch_v1 import (
            issue_strange_native_attestation_v1 as issue,
        )

        def issue_then_rotate(**params):
            proof = issue(**params)
            self.store.advance(
                expected_current_epoch=5,
                next_epoch=6,
                starts_at_seconds=720,
                observed_seconds=720,
            )
            return proof

        with patch(
            "koschei.strange_activated_candidate_launch_v1.issue_strange_native_attestation_v1",
            side_effect=issue_then_rotate,
        ):
            with self.assertRaises(StrangeActivatedCandidateError):
                self.launch()

    def test_clock_expiry_between_attestation_and_process_spawn_fails_closed(self):
        self.activate()
        from koschei.strange_activated_candidate_launch_v1 import (
            issue_strange_native_attestation_v1 as issue,
        )

        def issue_then_expire(**params):
            proof = issue(**params)
            self.now = 720
            return proof

        with patch(
            "koschei.strange_activated_candidate_launch_v1.issue_strange_native_attestation_v1",
            side_effect=issue_then_expire,
        ):
            with self.assertRaises(StrangeActivatedCandidateError):
                self.launch()

    def test_backward_clock_during_promotion_rejected(self):
        self.activate()
        readings = iter((600, 600, 599, 600, 600, 600, 600))
        with self.assertRaises(StrangeActivatedCandidateError):
            self.launch(seconds_reader=lambda: next(readings))


if __name__ == "__main__":
    unittest.main()
