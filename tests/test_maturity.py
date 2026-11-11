from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main
from koschei.maturity import MaturityEvidence, evaluate_maturity


class MaturityGateTests(unittest.TestCase):
    def _write_evidence(self, directory: str, checks: dict[str, object]) -> Path:
        path = Path(directory) / "maturity.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "koschei.maturity-evidence.v1",
                    "checks": checks,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_incubation_target_passes_with_core_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = self._write_evidence(
                directory,
                {
                    "compiler_tests": True,
                    "repository_truth": True,
                    "capability_security": True,
                },
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "maturity",
                        "--evidence",
                        str(evidence),
                        "--target",
                        "incubation",
                    ]
                )

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(report["ready"])
        self.assertFalse(report["production_integration_allowed"])
        self.assertEqual(report["missing_checks"], [])

    def test_production_target_fails_closed_when_evidence_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = self._write_evidence(
                directory,
                {
                    "compiler_tests": True,
                    "repository_truth": True,
                    "capability_security": True,
                },
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "maturity",
                        "--evidence",
                        str(evidence),
                        "--target",
                        "production",
                    ]
                )

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertFalse(report["ready"])
        self.assertIn("owner_approval", report["missing_checks"])
        self.assertFalse(report["production_integration_allowed"])

    def test_unknown_evidence_check_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = self._write_evidence(directory, {"magic_security": True})
            error = io.StringIO()
            with redirect_stderr(error):
                exit_code = main(["maturity", "--evidence", str(evidence)])

        self.assertEqual(exit_code, 2)
        self.assertIn("unsupported maturity checks", error.getvalue())

    def test_report_digest_is_deterministic(self) -> None:
        evidence_a = MaturityEvidence(
            checks={
                "compiler_tests": True,
                "repository_truth": True,
                "capability_security": True,
            }
        )
        evidence_b = MaturityEvidence(
            checks={
                "capability_security": True,
                "repository_truth": True,
                "compiler_tests": True,
            }
        )

        report_a = evaluate_maturity(evidence_a, "incubation")
        report_b = evaluate_maturity(evidence_b, "incubation")

        self.assertEqual(report_a.evidence_digest, report_b.evidence_digest)


if __name__ == "__main__":
    unittest.main()
