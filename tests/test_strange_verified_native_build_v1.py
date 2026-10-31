"""Sealed MIR-Go native provenance and failed-build negative tests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_native_admission_v1 import (
    StrangeNativeAdmissionError,
    verify_strange_native_admission_v1,
)
from koschei.strange_verified_native_build_v1 import (
    StrangeVerifiedNativeBuildError,
    verified_strange_native_build_v1,
)

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
KEY = b"A" * 32
ROOT_SEED = b"R" * 32


class StrangeVerifiedNativeBuildV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        self.current_epoch = 4
        self.now = 480
        self.continuity = bind_continuity_epoch_authority_v1(
            continuity_id="verified-build-test",
            epoch_reader=lambda: self.current_epoch,
        )

    def pinned_go(self):
        if not GO:
            self.skipTest("Go toolchain required")
        with Path(GO).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        return dict(go_executable=str(Path(GO).resolve()), expected_go_sha256=digest)

    def parameters(self):
        return dict(
            trust_plane_seed=ROOT_SEED,
            continuity=self.continuity,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="bank-a/native-1",
            veyra_digest="a" * 64,
            attestation_key=KEY,
        )

    def test_reject_unpinned_or_unavailable_compiler(self):
        with self.assertRaises(StrangeVerifiedNativeBuildError):
            verified_strange_native_build_v1(
                self.mir, **self.parameters(),
                go_executable="/nonexistent/nowhere/go",
                expected_go_sha256="0" * 64,
            )
        if GO:
            with self.assertRaisesRegex(StrangeVerifiedNativeBuildError, "pinned hash"):
                verified_strange_native_build_v1(
                    self.mir, **self.parameters(),
                    go_executable=str(Path(GO).resolve()),
                    expected_go_sha256="0" * 64,
                )

    def test_expired_window_and_invalid_timeout_fail_closed(self):
        if GO:
            self.now = 600
            with self.assertRaises(StrangeVerifiedNativeBuildError):
                verified_strange_native_build_v1(
                    self.mir, **self.parameters(), **self.pinned_go(),
                )
        for bad in (True, 0, 121, -1):
            with self.subTest(timeout=bad), self.assertRaises(StrangeVerifiedNativeBuildError):
                verified_strange_native_build_v1(
                    self.mir, **self.parameters(), **(self.pinned_go() if GO else {
                        "go_executable": "/missing/go", "expected_go_sha256": "0" * 64,
                    }),
                    build_timeout_seconds=bad,
                )

    @unittest.skipUnless(GO, "Go toolchain required for actual native provenance")
    def test_real_binary_matches_receipt_and_exact_attested_bytes(self):
        result = verified_strange_native_build_v1(
            self.mir, **self.parameters(), **self.pinned_go(),
        )
        self.assertFalse(result.authority)
        self.assertEqual(result.attestation.native_sha256, hashlib.sha256(result.binary).hexdigest())
        self.assertEqual(result.projection.source_sha256, result.attestation.source_sha256)
        self.assertNotIn(result.binary[:100].hex(), repr(result))
        verify_args = dict(
            attestation=result.attestation,
            native_binary=result.binary,
            expected_source_sha256=result.projection.source_sha256,
            deployment_id="bank-a/native-1",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            continuity=self.continuity,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=KEY,
        )
        verify_strange_native_admission_v1(**verify_args)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "hello-native"
            target.write_bytes(result.binary)
            target.chmod(0o700)
            completed = subprocess.run([str(target)], capture_output=True, check=False, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, b"Koschei\n1\n")
        with self.assertRaises(StrangeNativeAdmissionError):
            verify_strange_native_admission_v1(**(verify_args | {
                "native_binary": result.binary + b"changed"
            }))

    @unittest.skipUnless(GO, "Go toolchain required for pin preflight")
    def test_build_finishing_after_epoch_expiry_cannot_issue_attestation(self):
        args = self.pinned_go()

        def fake_build(command, *, cwd, env, capture_output, timeout, check):
            # Model the exact trusted command writing binary before a clock
            # transition; this is not a substitute for the real build test.
            Path(cwd, "native-program").write_bytes(b"synthetic-build-fixture")
            self.now = 600
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch(
            "koschei.strange_verified_native_build_v1.subprocess.run",
            side_effect=fake_build,
        ):
            with self.assertRaisesRegex(StrangeVerifiedNativeBuildError, "post-build"):
                verified_strange_native_build_v1(
                    self.mir, **self.parameters(), **args,
                )

    @unittest.skipUnless(GO, "Go toolchain required for pin preflight")
    def test_compiler_failure_and_timeout_cannot_issue_attestation(self):
        args = self.pinned_go()
        with patch(
            "koschei.strange_verified_native_build_v1.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, b"", b"failure"),
        ):
            with self.assertRaisesRegex(StrangeVerifiedNativeBuildError, "failed closed"):
                verified_strange_native_build_v1(self.mir, **self.parameters(), **args)
        with patch(
            "koschei.strange_verified_native_build_v1.subprocess.run",
            side_effect=subprocess.TimeoutExpired("go", 1),
        ):
            with self.assertRaisesRegex(StrangeVerifiedNativeBuildError, "failed closed"):
                verified_strange_native_build_v1(self.mir, **self.parameters(), **args)


if __name__ == "__main__":
    unittest.main()
