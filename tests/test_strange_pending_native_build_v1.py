"""Real Go prebuild of future epoch artifact, with strict no-authority tests."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1
from koschei.strange_pending_native_build_v1 import (
    PendingStrangeNativeBuildV1,
    StrangePendingNativeBuildError,
    prebuild_next_strange_native_v1,
)
from koschei.strange_pending_epoch_projection_v1 import (
    project_next_strange_epoch_go_v1,
)

GO = shutil.which("go")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(GO, "Go toolchain is needed for offline native prebuild")
class StrangePendingNativeBuildV1Tests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.work.name) / "continuity.sqlite3", continuity_id="tenant-a"
        )
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        self.now = 599
        self.go = str(Path(GO).resolve())
        with Path(self.go).open("rb") as stream:
            self.pin = hashlib.file_digest(stream, "sha256").hexdigest()
        self.args = dict(
            continuity_store=self.store,
            trust_plane_seed=b"K" * 32,
            expected_current_epoch=4,
            expected_current_start_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            go_executable=self.go,
            expected_go_sha256=self.pin,
        )

    def build(self, **changes):
        return prebuild_next_strange_native_v1(self.mir, **(self.args | changes))

    def test_real_native_compiles_before_boundary_without_authority(self):
        item = self.build()
        self.assertIsInstance(item, PendingStrangeNativeBuildV1)
        self.assertFalse(item.authority)
        self.assertEqual(item.pending_projection.target_epoch, 5)
        self.assertEqual(hashlib.sha256(item.binary).hexdigest(), item.native_sha256)
        self.assertNotIn(item.binary[:30].hex(), repr(item))
        item.assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(item, binary=item.binary + b"forgery").assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(item, authority=True).assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(item, native_sha256="0" * 64).assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(item, go_executable_sha256="f" * 63).assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(
                item,
                pending_projection=replace(item.pending_projection, target_epoch=7),
            ).assert_consistent()
        with self.assertRaises(StrangePendingNativeBuildError):
            replace(
                item,
                pending_projection=replace(item.pending_projection, authority=True),
            ).assert_consistent()
        with tempfile.TemporaryDirectory() as directory:
            native_path = Path(directory) / "candidate"
            native_path.write_bytes(item.binary)
            native_path.chmod(0o700)
            completed = subprocess.run([str(native_path)], capture_output=True, timeout=10)
            self.assertEqual(completed.stdout, b"Koschei\n1\n")
            self.assertEqual(completed.returncode, 0)
        # Handoff stage pins source and native identity without making epoch 5 active.
        handoff = StrangeEpochHandoffV1(self.store)
        stage = handoff.stage(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            source_sha256=item.pending_projection.source_sha256,
            native_binary=item.binary,
            seconds_reader=lambda: self.now,
            handoff_key=b"H" * 32,
        )
        self.assertEqual(stage.native_sha256, item.native_sha256)
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_wrong_compiler_pin_and_expired_window_rejected(self):
        with self.assertRaises(StrangePendingNativeBuildError):
            self.build(expected_go_sha256="0" * 64)
        self.now = 600
        with self.assertRaises(StrangePendingNativeBuildError):
            self.build()

    def test_compiler_failure_and_epoch_expiry_mid_build_rejected(self):
        with patch(
            "koschei.strange_pending_native_build_v1.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, b"", b"compiler failed"),
        ):
            with self.assertRaises(StrangePendingNativeBuildError):
                self.build()
        def finish_after_expiry(command, *, cwd, env, capture_output, timeout, check):
            Path(cwd, "native-program").write_bytes(b"test-binary")
            self.now = 600
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch(
            "koschei.strange_pending_native_build_v1.subprocess.run",
            side_effect=finish_after_expiry,
        ):
            with self.assertRaises(StrangePendingNativeBuildError):
                self.build()

    def test_bad_time_and_clock_rollback_during_build_rejected(self):
        for bad in (0, True, 121):
            with self.subTest(value=bad), self.assertRaises(StrangePendingNativeBuildError):
                self.build(build_timeout_seconds=bad)
        values = iter((599, 599, 598))
        with patch(
            "koschei.strange_pending_native_build_v1.subprocess.run",
            side_effect=lambda command, *, cwd, env, capture_output, timeout, check: (
                Path(cwd, "native-program").write_bytes(b"test-binary"),
                subprocess.CompletedProcess(command, 0, b"", b""),
            )[1],
        ):
            with self.assertRaises(StrangePendingNativeBuildError):
                self.build(seconds_reader=lambda: next(values))


if __name__ == "__main__":
    unittest.main()
