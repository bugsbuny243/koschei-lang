"""Commercial 0.10.0 deliverables must be repeatable and tied to a full CI receipt."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from koschei.local_validation_v1 import (
    seal_local_validation_receipt_v1, seal_local_validation_step_v1,
)
from tools.commercial_release_candidate_v1 import (
    CommercialCandidateError, SCHEMA, build_candidate, validate_receipt,
)
from tools.polar_bundle_v1 import version

SHA = "a" * 40
HEX = hashlib.sha256(b"test-output").hexdigest()


def receipt_data(source_commit: str = SHA) -> dict:
    step = seal_local_validation_step_v1(
        step_id="fixture-full-suite", command=("python", "-m", "pytest", "-q", "tests"),
        returncode=0, stdout_sha256=HEX, stderr_sha256=HEX,
    )
    receipt = seal_local_validation_receipt_v1(
        source_commit=source_commit,
        checkout_clean=True,
        profile="full",
        python_version="Python 3.12",
        go_version="go1.24",
        platform="test-fixture",
        steps=(step,),
    )
    return asdict(receipt)


class CommercialReleaseCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="koschei-sale-candidate-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / "validated.json"
        self.receipt.write_text(json.dumps(receipt_data()), encoding="utf-8")

    def test_positive_candidate_has_zip_sha_manifest_and_pilot_evidence(self) -> None:
        output_dir = self.root / "ship"
        with mock.patch("tools.commercial_release_candidate_v1._source_commit", return_value=SHA):
            result = build_candidate(output_dir, self.receipt, version())

        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["source_commit"], SHA)
        self.assertEqual(result["version"], version())
        self.assertTrue(result["reproducible_build"])
        self.assertTrue(result["full_validation_release_eligible"])
        self.assertFalse(result["publicly_published"])
        self.assertFalse(result["store_checkout_verified"])

        zip_path = output_dir / result["artifact_name"]
        binary = zip_path.read_bytes()
        digest = hashlib.sha256(binary).hexdigest()
        self.assertEqual(digest, result["artifact_sha256"])
        self.assertEqual(len(binary), result["artifact_size_bytes"])
        self.assertEqual(
            (output_dir / "SHA256SUMS").read_text(encoding="utf-8"),
            f"{digest}  {zip_path.name}\n",
        )
        saved = json.loads(
            (output_dir / "candidate-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved, result)
        evidence = json.loads(
            (output_dir / "customer-security-evidence.json").read_text(encoding="utf-8")
        )
        self.assertTrue(evidence["pilot_checks_passed"])
        self.assertFalse(evidence["approved_for_production"])

    def test_wrong_expected_version_aborts_before_output_creation(self) -> None:
        out = self.root / "wrong-version"
        with mock.patch("tools.commercial_release_candidate_v1._source_commit", return_value=SHA):
            with self.assertRaisesRegex(CommercialCandidateError, "version mismatch"):
                build_candidate(out, self.receipt, "999.999")
        self.assertFalse(out.exists())

    def test_cross_commit_receipt_refused(self) -> None:
        with self.assertRaisesRegex(CommercialCandidateError, "exact-head"):
            validate_receipt(self.receipt, "b" * 40)

    def test_tampered_receipt_refused(self) -> None:
        tampered = receipt_data()
        tampered["release_eligible"] = False
        self.receipt.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(CommercialCandidateError, "exact-head"):
            validate_receipt(self.receipt, SHA)

    def test_failed_step_receipt_refused_even_if_checksums_are_valid(self) -> None:
        failed_step = seal_local_validation_step_v1(
            step_id="broken", command=("false",), returncode=1,
            stdout_sha256=HEX, stderr_sha256=HEX,
        )
        receipt = seal_local_validation_receipt_v1(
            source_commit=SHA, checkout_clean=True, profile="full",
            python_version="Python 3.12", go_version="go1.24",
            platform="test-fixture", steps=(failed_step,),
        )
        self.receipt.write_text(json.dumps(asdict(receipt)), encoding="utf-8")
        with self.assertRaisesRegex(CommercialCandidateError, "exact-head"):
            validate_receipt(self.receipt, SHA)

    def test_existing_nonempty_destination_refused(self) -> None:
        out = self.root / "occupied"
        out.mkdir()
        (out / "existing").write_text("unrelated", encoding="utf-8")
        with mock.patch("tools.commercial_release_candidate_v1._source_commit", return_value=SHA):
            with self.assertRaisesRegex(CommercialCandidateError, "must be empty"):
                build_candidate(out, self.receipt, version())
        self.assertEqual((out / "existing").read_text(encoding="utf-8"), "unrelated")


if __name__ == "__main__":
    unittest.main()
