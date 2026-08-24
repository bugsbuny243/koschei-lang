from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.adversarial_lab_v2 import (
    MIN_TOTAL_ATTACK_TESTS,
    REQUIRED_GATES,
    evaluate_release_v2,
)


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
        return True, gate.min_tests, "ok"

    def test_living_local_floors_naturally_meet_global_budget(self):
        self.assertEqual(MIN_TOTAL_ATTACK_TESTS, 141)
        self.assertEqual(sum(gate.min_tests for gate in REQUIRED_GATES), 141)

    def test_native_galaxy_adversarial_gates_are_required(self):
        expected = {
            "distribution-shift-observer": (
                "tests/test_distribution_shift_observer_v1.py",
                5,
            ),
            "galaxy-learning-resistance": (
                "tests/test_galaxy_adversarial_learning_v1.py",
                6,
            ),
            "khar-failure-independence": (
                "tests/test_khar_failure_independence_v1.py",
                7,
            ),
            "galaxy-execution-gate": (
                "tests/test_galaxy_execution_gate_v1.py",
                5,
            ),
        }
        actual = {
            gate.gate_id: (gate.test_file, gate.min_tests)
            for gate in REQUIRED_GATES
            if gate.gate_id in expected
        }
        self.assertEqual(actual, expected)

    def test_all_required_suites_are_commercial_ready_at_exact_floor(self):
        report = evaluate_release_v2(
            candidate_id="rc",
            repo_root=self.root(),
            runner=self.runner,
        )
        self.assertTrue(report.commercial_ready)
        self.assertEqual(report.total_tests_run, MIN_TOTAL_ATTACK_TESTS)
        self.assertTrue(all(result.passed for result in report.results))

    def test_missing_suite_fails_closed(self):
        root = self.root()
        target = next(
            gate
            for gate in REQUIRED_GATES
            if gate.gate_id == "galaxy-learning-resistance"
        )
        (root / target.test_file).unlink()
        report = evaluate_release_v2(
            candidate_id="rc",
            repo_root=root,
            runner=self.runner,
        )
        self.assertFalse(report.commercial_ready)
        failed = next(
            result for result in report.results if result.gate_id == target.gate_id
        )
        self.assertFalse(failed.passed)
        self.assertEqual(failed.detail, "required suite missing")

    def test_one_test_shrink_fails_closed_even_when_runner_claims_pass(self):
        root = self.root()
        target = next(
            gate
            for gate in REQUIRED_GATES
            if gate.gate_id == "khar-failure-independence"
        )

        def shrunk_runner(test_file):
            gate = next(item for item in REQUIRED_GATES if item.test_file == test_file)
            count = gate.min_tests - 1 if gate.gate_id == target.gate_id else gate.min_tests
            return True, count, "runner green"

        report = evaluate_release_v2(
            candidate_id="rc-shrink",
            repo_root=root,
            runner=shrunk_runner,
        )
        self.assertFalse(report.commercial_ready)
        failed = next(
            result for result in report.results if result.gate_id == target.gate_id
        )
        self.assertFalse(failed.passed)
        self.assertIn("test-count shrink detected", failed.detail)

    def test_digest_is_deterministic(self):
        root = self.root()
        first = evaluate_release_v2(
            candidate_id="rc",
            repo_root=root,
            runner=self.runner,
        )
        second = evaluate_release_v2(
            candidate_id="rc",
            repo_root=root,
            runner=self.runner,
        )
        self.assertEqual(first.report_sha256, second.report_sha256)


if __name__ == "__main__":
    unittest.main()
