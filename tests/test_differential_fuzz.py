from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from koschei.differential_fuzz import (
    DifferentialFuzzError,
    generate_cases,
    run_differential_fuzz,
    write_differential_fuzz_report,
)


class DifferentialFuzzTests(unittest.TestCase):
    def test_generation_is_deterministic_and_template_balanced(self) -> None:
        left = generate_cases(seed=20260809, case_count=8)
        right = generate_cases(seed=20260809, case_count=8)
        other = generate_cases(seed=20260810, case_count=8)
        self.assertEqual(left, right)
        self.assertNotEqual(left, other)
        self.assertEqual(
            [item.template for item in left],
            ["arithmetic", "branch", "loop", "function"] * 2,
        )
        self.assertEqual(len({item.case_id for item in left}), 8)

    def test_case_limits_fail_closed(self) -> None:
        for count in (0, 257):
            with self.assertRaises(DifferentialFuzzError):
                generate_cases(seed=1, case_count=count)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native differential fuzzing")
    def test_real_interpreter_native_differential_run(self) -> None:
        report = run_differential_fuzz(seed=101, case_count=4)
        self.assertEqual(report["schema_version"], "koschei.differential-fuzz-report.v1")
        self.assertEqual(report["state"], "passed_differential_fuzz")
        self.assertEqual(report["case_count"], 4)
        self.assertTrue(report["interpreter_native_byte_identical"])
        self.assertFalse(report["adversarial_capability_tests_observed"])
        self.assertFalse(report["production_integration_allowed"])
        self.assertEqual(len(report["report_digest"]), 64)
        self.assertEqual(len(report["corpus_sha256"]), 64)

    def test_report_write_is_no_replace(self) -> None:
        payload = {
            "schema_version": "koschei.differential-fuzz-report.v1",
            "state": "passed_differential_fuzz",
            "generator_version": "test",
            "seed": 1,
            "case_count": 1,
            "cases": [],
            "corpus_sha256": "0" * 64,
            "interpreter_native_byte_identical": True,
            "adversarial_capability_tests_observed": False,
            "production_integration_allowed": False,
            "report_digest": "1" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_differential_fuzz_report(payload, path)
            with self.assertRaises(DifferentialFuzzError):
                write_differential_fuzz_report(payload, path)


if __name__ == "__main__":
    unittest.main()
