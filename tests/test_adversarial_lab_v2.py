from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.adversarial_lab_v2 import MIN_TOTAL_ATTACK_TESTS, REQUIRED_GATES, evaluate_release_v2


class AdversarialLabV2Tests(unittest.TestCase):
    def root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for gate in REQUIRED_GATES:
            path = root / gate.test_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# suite\n", encoding="utf-8")
        return root

    def runner(self, test_file):
        gate = next(item for item in REQUIRED_GATES if item.test_file == test_file)
        local_floor = sum(item.min_tests for item in REQUIRED_GATES)
        surplus = max(0, MIN_TOTAL_ATTACK_TESTS - local_floor)
        boost_gate = REQUIRED_GATES[0]
        tests_run = gate.min_tests + (surplus if gate.gate_id == boost_gate.gate_id else 0)
        return True, tests_run, "ok"

    def test_140_global_baseline_is_not_the_sum_of_local_floors(self):
        self.assertEqual(MIN_TOTAL_ATTACK_TESTS, 140)
        self.assertLessEqual(sum(gate.min_tests for gate in REQUIRED_GATES), MIN_TOTAL_ATTACK_TESTS)

    def test_distribution_shift_is_required(self):
        gate = next(item for item in REQUIRED_GATES if item.gate_id == "distribution-shift-observer")
        self.assertEqual(gate.min_tests, 5)

    def test_all_required_suites_and_global_budget_are_commercial_ready(self):
        report = evaluate_release_v2(candidate_id="rc", repo_root=self.root(), runner=self.runner)
        self.assertTrue(report.commercial_ready)
        self.assertGreaterEqual(report.total_tests_run, MIN_TOTAL_ATTACK_TESTS)
        self.assertTrue(all(result.passed for result in report.results))

    def test_missing_suite_fails_closed_even_if_global_count_is_high(self):
        root = self.root()
        (root / "tests/test_distribution_shift_observer_v1.py").unlink()
        report = evaluate_release_v2(candidate_id="rc", repo_root=root, runner=self.runner)
        self.assertFalse(report.commercial_ready)
        failed = next(result for result in report.results if result.gate_id == "distribution-shift-observer")
        self.assertFalse(failed.passed)
        self.assertEqual(failed.detail, "required suite missing")

    def test_digest_is_deterministic(self):
        root = self.root()
        first = evaluate_release_v2(candidate_id="rc", repo_root=root, runner=self.runner)
        second = evaluate_release_v2(candidate_id="rc", repo_root=root, runner=self.runner)
        self.assertEqual(first.report_sha256, second.report_sha256)


if __name__ == "__main__":
    unittest.main()
