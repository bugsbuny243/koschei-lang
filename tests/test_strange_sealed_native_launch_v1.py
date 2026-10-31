"""Linux sealed-memfd launch checks for exact Strange native artifact bytes."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_native_admission_v1 import issue_strange_native_attestation_v1
from koschei.strange_representation_epoch_v1 import project_strange_epoch_go_v1
from koschei.strange_sealed_native_launch_v1 import (
    StrangeSealedNativeLaunchError,
    _sealed_native_fd,
    run_strange_sealed_native_v1,
)


ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
SUPPORTED = sys.platform == "linux" and GO is not None and hasattr(os, "memfd_create")


@unittest.skipUnless(SUPPORTED, "Linux + Go required for sealed native execution")
class StrangeSealedNativeLaunchV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        cls.mir = require_mir(graph)
        continuity = bind_continuity_epoch_authority_v1(
            continuity_id="sealed-launch-test",
            epoch_reader=lambda: 4,
        )
        source, cls.receipt = project_strange_epoch_go_v1(
            cls.mir,
            trust_plane_seed=b"K" * 32,
            continuity=continuity,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: 480,
            deployment_id="galaxy-a/deploy",
            veyra_digest="a" * 64,
        )
        source_file = Path(cls.work.name) / "program.go"
        binary_file = Path(cls.work.name) / "program"
        source_file.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            [
                GO, "build", "-trimpath", "-buildvcs=false",
                "-ldflags=-buildid=", "-o", str(binary_file), str(source_file),
            ],
            capture_output=True, check=False, text=True, timeout=90,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr)
        cls.binary = binary_file.read_bytes()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "work"):
            cls.work.cleanup()

    def setUp(self):
        self.work_db = tempfile.TemporaryDirectory()
        self.addCleanup(self.work_db.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.work_db.name) / "continuity.sqlite3",
            continuity_id="galaxy-a",
        )
        self.addCleanup(self.store.close)
        self.now = 480
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.key = b"A" * 32
        self.proof = issue_strange_native_attestation_v1(
            receipt=self.receipt, native_binary=self.binary,
            deployment_id="galaxy-a/deploy", veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4, starts_at_seconds=480,
            seconds_reader=lambda: self.now, attestation_key=self.key,
        )

    def launch(self, **changes):
        args = dict(
            continuity_store=self.store,
            attestation=self.proof,
            native_binary=self.binary,
            expected_source_sha256=self.receipt.source_sha256,
            deployment_id="galaxy-a/deploy",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            expected_epoch=4,
            expected_start_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=self.key,
        )
        args.update(changes)
        return run_strange_sealed_native_v1(**args)

    def test_executes_immutable_attested_native_bytes(self):
        result = self.launch()
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(result.stdout, b"Koschei\n1\n")
        self.assertFalse(result.authority)
        self.assertEqual(result.epoch_at_launch, 4)
        self.assertNotIn(result.stdout.decode().strip(), repr(result))

    def test_fd_is_immutable_after_sealing(self):
        fd = _sealed_native_fd(self.binary)
        try:
            seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            required = (
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
            )
            self.assertEqual(seals & required, required)
            os.lseek(fd, 0, os.SEEK_SET)
            with self.assertRaises(OSError):
                os.write(fd, b"tamper")
        finally:
            os.close(fd)

    def test_rejects_wrong_native_bytes_tenant_and_epoch(self):
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch(native_binary=self.binary + b"modified")
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch(deployment_id="galaxy-b/deploy")
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch(veyra_digest="b" * 64)
        self.now = 600
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch()
        self.store.advance(
            expected_current_epoch=4, next_epoch=5,
            starts_at_seconds=600, observed_seconds=600,
        )
        self.now = 599
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch()

    def test_copy_crossing_epoch_boundary_cannot_launch(self):
        real_copy = _sealed_native_fd

        def copy_then_expire(native_binary):
            fd = real_copy(native_binary)
            self.now = 600
            return fd

        with patch(
            "koschei.strange_sealed_native_launch_v1._sealed_native_fd",
            side_effect=copy_then_expire,
        ):
            with self.assertRaises(StrangeSealedNativeLaunchError):
                self.launch()

    def test_invalid_timeout_and_empty_binary_fail_closed(self):
        for timeout in (0, True, -1, 31):
            with self.subTest(timeout=timeout), self.assertRaises(StrangeSealedNativeLaunchError):
                self.launch(timeout_seconds=timeout)
        with self.assertRaises(StrangeSealedNativeLaunchError):
            self.launch(native_binary=b"")


if __name__ == "__main__":
    unittest.main()
