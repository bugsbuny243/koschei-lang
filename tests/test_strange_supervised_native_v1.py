"""Local sealed-process expiry supervision integration and negative tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_native_admission_v1 import issue_strange_native_attestation_v1
from koschei.strange_representation_epoch_v1 import project_strange_epoch_go_v1
from koschei.strange_supervised_native_v1 import (
    StrangeSupervisedNativeError,
    run_strange_supervised_native_v1,
)

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
SUPPORTED = sys.platform == "linux" and GO is not None


@unittest.skipUnless(SUPPORTED, "Linux + Go required for native epoch supervision")
class StrangeSupervisedNativeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.work = tempfile.TemporaryDirectory()
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        cls.mir = require_mir(graph)
        authority = bind_continuity_epoch_authority_v1(
            continuity_id="test-supervised-mir", epoch_reader=lambda: 4,
        )
        source, cls.receipt = project_strange_epoch_go_v1(
            cls.mir,
            trust_plane_seed=b"S" * 32,
            continuity=authority,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: 480,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
        )
        cls.binary = cls._compile("hello", source)
        # This extra test fixture is ONLY for observing supervisor behaviour.
        # The low-level issuer can attest arbitrary bytes; its existence is
        # not a sealed MIR -> binary supply-chain proof.
        cls.sleep_binary = cls._compile(
            "sleep",
            'package main\nimport "time"\nfunc main() { time.Sleep(4 * time.Second) }\n',
        )

    @classmethod
    def _compile(cls, name: str, source: str) -> bytes:
        root = Path(cls.work.name)
        path = root / (name + ".go")
        output = root / name
        path.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [GO, "build", "-trimpath", "-buildvcs=false",
             "-ldflags=-buildid=", "-o", str(output), str(path)],
            capture_output=True, text=True, timeout=90, check=False,
        )
        if proc.returncode:
            raise AssertionError(proc.stderr)
        return output.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "work"):
            cls.work.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.tmp.name) / "continuity.sqlite3", continuity_id="galaxy-a"
        )
        self.addCleanup(self.store.close)
        self.now = 480
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.key = b"A" * 32

    def proof(self, binary: bytes):
        return issue_strange_native_attestation_v1(
            receipt=self.receipt,
            native_binary=binary,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=self.key,
        )

    def run_native(self, *, binary=None, proof=None, **changes):
        native = self.binary if binary is None else binary
        args = dict(
            continuity_store=self.store,
            attestation=self.proof(native) if proof is None else proof,
            native_binary=native,
            expected_source_sha256=self.receipt.source_sha256,
            deployment_id="galaxy-a/native",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            expected_epoch=4,
            expected_start_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=self.key,
            poll_interval_seconds=0.02,
        )
        args.update(changes)
        return run_strange_supervised_native_v1(**args)

    def test_real_native_mir_output_under_supervisor(self) -> None:
        result = self.run_native()
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(result.stdout, b"Koschei\n1\n")
        self.assertEqual(result.observed_epoch, 4)
        self.assertGreater(result.checks, 0)
        self.assertFalse(result.authority)
        self.assertNotIn("Koschei", repr(result))

    def test_wrong_tenant_modified_bytes_and_expired_window_fail(self) -> None:
        proof = self.proof(self.binary)
        with self.assertRaises(StrangeSupervisedNativeError):
            self.run_native(binary=self.binary + b"tamper", proof=proof)
        with self.assertRaises(StrangeSupervisedNativeError):
            self.run_native(proof=proof, deployment_id="galaxy-b/native")
        self.now = 600
        with self.assertRaises(StrangeSupervisedNativeError):
            self.run_native(proof=proof)

    def test_long_running_native_is_stopped_after_epoch_advancement(self) -> None:
        native = self.sleep_binary
        proof = self.proof(native)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_native, binary=native, proof=proof)
            time.sleep(0.20)
            self.store.advance(
                expected_current_epoch=4, next_epoch=5,
                starts_at_seconds=600, observed_seconds=600,
            )
            with self.assertRaises(StrangeSupervisedNativeError):
                future.result(timeout=4)

    def test_long_running_native_is_stopped_at_clock_expiry(self) -> None:
        native = self.sleep_binary
        proof = self.proof(native)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_native, binary=native, proof=proof)
            time.sleep(0.20)
            self.now = 600
            with self.assertRaises(StrangeSupervisedNativeError):
                future.result(timeout=4)

    def test_local_monotonic_deadline_limits_frozen_clock(self) -> None:
        native = self.sleep_binary
        proof = self.proof(native)
        start = time.monotonic()
        with self.assertRaises(StrangeSupervisedNativeError):
            self.run_native(binary=native, proof=proof, run_timeout_seconds=1)
        self.assertLess(time.monotonic() - start, 3.5)

    def test_invalid_supervision_limits_fail_closed(self) -> None:
        for value in (0, True, 121):
            with self.subTest(timeout=value), self.assertRaises(StrangeSupervisedNativeError):
                self.run_native(run_timeout_seconds=value)
        for value in (0.0, True, 1.0, float("nan")):
            with self.subTest(interval=value), self.assertRaises(StrangeSupervisedNativeError):
                self.run_native(poll_interval_seconds=value)
        for value in (0, False, -1, 10_000_001):
            with self.subTest(limit=value), self.assertRaises(StrangeSupervisedNativeError):
                self.run_native(max_output_bytes=value)


if __name__ == "__main__":
    unittest.main()
