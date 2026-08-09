from __future__ import annotations

import unittest

from koschei.maturity import MaturityEvidence, evaluate_maturity


class MaturityReferenceTrustTests(unittest.TestCase):
    def test_v2_manual_core_checks_do_not_satisfy_reference_trust(self) -> None:
        evidence = MaturityEvidence(
            checks={
                "compiler_tests": True,
                "repository_truth": True,
                "capability_security": True,
                "syntax_stability": True,
                "type_system_stability": True,
                "package_integrity": True,
                "reproducible_builds": True,
                "interpreter_native_parity": True,
                "real_programs": True,
            },
            schema_version="koschei.maturity-evidence.v2",
            canonical_payload={"schema_version": "synthetic-test-only"},
        )
        report = evaluate_maturity(evidence, "reference")
        self.assertFalse(report.ready)
        self.assertIn("compiler_tests", report.missing_checks)
        self.assertIn("repository_truth", report.missing_checks)
        self.assertIn("capability_security", report.missing_checks)

    def test_incubation_still_accepts_manual_core_evidence(self) -> None:
        evidence = MaturityEvidence(
            checks={
                "compiler_tests": True,
                "repository_truth": True,
                "capability_security": True,
            }
        )
        report = evaluate_maturity(evidence, "incubation")
        self.assertTrue(report.ready)


if __name__ == "__main__":
    unittest.main()
