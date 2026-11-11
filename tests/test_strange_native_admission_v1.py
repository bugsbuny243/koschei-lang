"""Adversarial negative tests for authority-free native Strange admission."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.mir import require_mir
from koschei.modules import load_graph, check_graph
from koschei.strange_representation_epoch_v1 import project_strange_epoch_go_v1
from koschei.strange_native_admission_v1 import (
    StrangeNativeAdmissionError,
    issue_strange_native_attestation_v1,
    verify_strange_native_admission_v1,
)

ROOT = Path(__file__).resolve().parents[1]
KEY = b"A" * 32


class StrangeNativeAdmissionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.epoch = 4
        self.now = 480
        self.continuity = bind_continuity_epoch_authority_v1(
            continuity_id="native-attestation-test",
            epoch_reader=lambda: self.epoch,
        )
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        source, self.receipt = project_strange_epoch_go_v1(
            self.mir,
            trust_plane_seed=b"S" * 32,
            continuity=self.continuity,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="bank-a/worker",
            veyra_digest="a" * 64,
        )
        self.source = source
        self.binary = b"verified-native-build-fixture"
        self.arguments = dict(
            deployment_id="bank-a/worker",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            continuity=self.continuity,
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=KEY,
        )

    def attestation(self):
        return issue_strange_native_attestation_v1(
            receipt=self.receipt, native_binary=self.binary, **self.arguments,
        )

    def verify(self, attestation, *, binary=None, **overrides):
        params = dict(self.arguments)
        params.update(overrides)
        verify_strange_native_admission_v1(
            attestation=attestation,
            native_binary=self.binary if binary is None else binary,
            expected_source_sha256=self.receipt.source_sha256,
            **params,
        )

    def test_valid_native_artifact_is_admitted_without_authority(self):
        evidence = self.attestation()
        self.verify(evidence)
        self.assertFalse(evidence.authority)
        self.assertEqual(evidence.expires_before_seconds, 600)
        self.assertNotIn(self.arguments["deployment_id"], repr(evidence))
        self.assertNotIn(self.mir.fingerprint, repr(evidence))

    @unittest.skipUnless(shutil.which("go"), "Go toolchain required for native artifact parity")
    def test_real_native_executable_provenance_and_tamper_denial(self):
        """Exercise source->Go build->native bytes->attestation->runtime parity."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "main.go"
            binary_file = root / "hello"
            source_file.write_text(self.source, encoding="utf-8")
            build = subprocess.run(
                [
                    shutil.which("go"), "build", "-trimpath", "-buildvcs=false",
                    "-ldflags=-buildid=", "-o", str(binary_file), str(source_file),
                ],
                capture_output=True, text=True, check=False, timeout=90,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            binary = binary_file.read_bytes()
            evidence = issue_strange_native_attestation_v1(
                receipt=self.receipt, native_binary=binary, **self.arguments,
            )
            self.verify(evidence, binary=binary)
            completed = subprocess.run(
                [str(binary_file)], capture_output=True, check=False, timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, b"Koschei\n1\n")
            with self.assertRaises(StrangeNativeAdmissionError):
                self.verify(evidence, binary=binary + b"tampered")

    def test_wrong_binary_source_scope_or_attestation_key_fail_closed(self):
        evidence = self.attestation()
        cases = (
            dict(binary=b"modified executable"),
            dict(deployment_id="bank-b/worker"),
            dict(veyra_digest="b" * 64),
            dict(mir_fingerprint="b" * 64),
            dict(attestation_key=b"B" * 32),
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(StrangeNativeAdmissionError):
                self.verify(evidence, **overrides)
        with self.assertRaises(StrangeNativeAdmissionError):
            verify_strange_native_admission_v1(
                attestation=evidence, native_binary=self.binary,
                expected_source_sha256="c" * 64, **self.arguments
            )

    def test_tampered_attestation_and_caller_constructed_report_fail_closed(self):
        original = self.attestation()
        for changed in (
            replace(original, attestation_mac="0" * 64),
            replace(original, native_sha256="1" * 64),
            replace(original, scope_binding="2" * 64),
            replace(original, authority=True),
            replace(original, version=2),
            replace(original, expires_before_seconds=999),
        ):
            with self.subTest(changed=changed), self.assertRaises(StrangeNativeAdmissionError):
                self.verify(changed)

    def test_malformed_caller_fields_fail_closed(self):
        original = self.attestation()
        for field in ("source_sha256", "native_sha256", "scope_binding", "attestation_mac"):
            for invalid in (None, 123, "", "Z" * 64):
                with self.subTest(field=field, invalid=invalid):
                    forged = replace(original, **{field: invalid})
                    with self.assertRaises(StrangeNativeAdmissionError):
                        self.verify(forged)

    def test_boundary_t119_valid_t120_invalid(self):
        evidence = self.attestation()
        self.now = 599
        self.verify(evidence)
        self.now = 600
        with self.assertRaises(StrangeNativeAdmissionError):
            self.verify(evidence)

    def test_revoked_epoch_and_false_clock_fail_closed(self):
        evidence = self.attestation()
        self.epoch += 1
        with self.assertRaises(StrangeNativeAdmissionError):
            self.verify(evidence)
        self.epoch -= 1
        with self.assertRaises(StrangeNativeAdmissionError):
            self.verify(evidence, seconds_reader=lambda: True)

    def test_attestation_cannot_be_issued_for_expired_receipt(self):
        self.now = 600
        with self.assertRaises(StrangeNativeAdmissionError):
            self.attestation()
        self.now = 480
        with self.assertRaises(StrangeNativeAdmissionError):
            issue_strange_native_attestation_v1(
                receipt=replace(self.receipt, source_sha256="z" * 64),
                native_binary=self.binary, **self.arguments,
            )

    def test_time_and_epoch_race_fail_closed_on_verify(self):
        evidence = self.attestation()
        calls = [0]

        def advancing_reader():
            calls[0] += 1
            if calls[0] >= 2:
                self.now = 600
            return self.now

        with self.assertRaises(StrangeNativeAdmissionError):
            self.verify(evidence, seconds_reader=advancing_reader)


if __name__ == "__main__":
    unittest.main()
