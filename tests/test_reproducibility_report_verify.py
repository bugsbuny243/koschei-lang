from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from koschei.build_manifest import NativeBuildManifest
from koschei.reproducibility import (
    ReproducibilityError,
    compare_verified_builds,
    load_reproducibility_report,
    verify_reproducibility_report,
    write_reproducibility_report,
)


class ReproducibilityReportVerificationTests(unittest.TestCase):
    def _manifest(
        self,
        *,
        artifact: str = "a",
        toolchain: str = "go version go1.24 fixture",
        manifest: str = "b",
    ) -> NativeBuildManifest:
        return NativeBuildManifest(
            artifact_name="app",
            artifact_size=128,
            artifact_sha256=artifact * 64,
            module_lock_digest="1" * 64,
            mir_version="1",
            mir_fingerprint="2" * 64,
            compiler_version="0.10.0",
            backend="go-native",
            backend_toolchain=toolchain,
            manifest_digest=manifest * 64,
        )

    def test_report_round_trip_verifies_against_exact_manifests(self) -> None:
        left = self._manifest(artifact="a", manifest="b")
        right = self._manifest(artifact="a", manifest="c")
        report = compare_verified_builds(left, right)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reproducibility.json"
            write_reproducibility_report(report, path)
            loaded = load_reproducibility_report(path)

        verified = verify_reproducibility_report(loaded, left, right)
        self.assertEqual(verified.status, "byte_identical")
        self.assertTrue(verified.byte_reproducible)

    def test_report_from_different_build_pair_is_rejected(self) -> None:
        left = self._manifest(artifact="a", manifest="b")
        right = self._manifest(artifact="a", manifest="c")
        different_right = self._manifest(
            artifact="d",
            toolchain="go version go1.25 other",
            manifest="e",
        )
        report = compare_verified_builds(left, different_right)

        with self.assertRaisesRegex(ReproducibilityError, "supplied verified builds"):
            verify_reproducibility_report(report, left, right)

    def test_tampered_report_digest_is_rejected(self) -> None:
        report = compare_verified_builds(
            self._manifest(artifact="a", manifest="b"),
            self._manifest(artifact="a", manifest="c"),
        )
        payload = report.to_dict()
        payload["byte_reproducible"] = False

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reproducibility.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReproducibilityError, "internally inconsistent"):
                load_reproducibility_report(path)

    def test_unknown_report_fields_are_rejected(self) -> None:
        report = compare_verified_builds(
            self._manifest(artifact="a", manifest="b"),
            self._manifest(artifact="a", manifest="c"),
        )
        payload = report.to_dict()
        payload["claimed_safe"] = True

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reproducibility.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReproducibilityError, "unsupported fields"):
                load_reproducibility_report(path)


if __name__ == "__main__":
    unittest.main()
