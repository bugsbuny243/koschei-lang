from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.adversarial_lab_v1 import MIN_TOTAL_ATTACK_TESTS, REQUIRED_GATES, evaluate_release


class AdversarialLabV1Tests(unittest.TestCase):
    def _root_with_required_suites(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for gate in REQUIRED_GATES:
            path = root / gate.test_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# synthetic suite marker\n", encoding="utf-8")
        return root

    def _baseline_runner(self, test_file: str):
        gate = next(g for g in REQUIRED_GATES if g.test_file == test_file)
        return True, gate.min_tests, "ok"

    def test_all_gates_must_pass_for_commercial_ready(self):
        root = self._root_with_required_suites()
        report = evaluate_release(candidate_id="rc-1", repo_root=root, runner=self._baseline_runner)
        self.assertTrue(report.commercial_ready)
        self.assertEqual(len(report.results), len(REQUIRED_GATES))
        self.assertGreaterEqual(report.total_tests_run, MIN_TOTAL_ATTACK_TESTS)
        self.assertEqual(report.minimum_total_tests, MIN_TOTAL_ATTACK_TESTS)
        self.assertEqual(len(report.report_sha256), 64)

    def test_one_failed_gate_blocks_release(self):
        root = self._root_with_required_suites()
        def runner(test_file: str):
            gate = next(g for g in REQUIRED_GATES if g.test_file == test_file)
            if test_file.endswith("test_decoy_attack_simulation_v1.py"):
                return False, gate.min_tests, "attack escaped expected invariant"
            return True, gate.min_tests, "ok"
        report = evaluate_release(candidate_id="rc-2", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        self.assertEqual(sum(not r.passed for r in report.results), 1)

    def test_missing_suite_fails_closed_without_runner_call(self):
        root = self._root_with_required_suites()
        missing = root / REQUIRED_GATES[0].test_file
        missing.unlink()
        calls = []
        def runner(test_file: str):
            calls.append(test_file)
            gate = next(g for g in REQUIRED_GATES if g.test_file == test_file)
            return True, gate.min_tests, "ok"
        report = evaluate_release(candidate_id="rc-3", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        first = next(r for r in report.results if r.gate_id == REQUIRED_GATES[0].gate_id)
        self.assertEqual(first.detail, "required suite missing")
        self.assertNotIn(REQUIRED_GATES[0].test_file, calls)

    def test_zero_test_suite_is_failure(self):
        root = self._root_with_required_suites()
        report = evaluate_release(candidate_id="rc-4", repo_root=root, runner=lambda _: (True, 0, "empty"))
        self.assertFalse(report.commercial_ready)
        self.assertTrue(all(not r.passed for r in report.results))

    def test_runner_exception_fails_closed(self):
        root = self._root_with_required_suites()
        def runner(_):
            raise RuntimeError("boom")
        report = evaluate_release(candidate_id="rc-5", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        self.assertTrue(all(r.detail == "runner error: RuntimeError" for r in report.results))

    def test_report_digest_is_deterministic(self):
        root = self._root_with_required_suites()
        a = evaluate_release(candidate_id="rc-6", repo_root=root, runner=self._baseline_runner)
        b = evaluate_release(candidate_id="rc-6", repo_root=root, runner=self._baseline_runner)
        self.assertEqual(a.report_sha256, b.report_sha256)

    def test_per_gate_test_count_shrink_blocks_release(self):
        root = self._root_with_required_suites()
        target = REQUIRED_GATES[0]
        def runner(test_file: str):
            gate = next(g for g in REQUIRED_GATES if g.test_file == test_file)
            count = gate.min_tests - 1 if gate.gate_id == target.gate_id else gate.min_tests
            return True, count, "runner green"
        report = evaluate_release(candidate_id="rc-shrink", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        result = next(r for r in report.results if r.gate_id == target.gate_id)
        self.assertFalse(result.passed)
        self.assertIn("test-count shrink detected", result.detail)

    def test_baseline_attack_budget_includes_living_synthetic_system(self):
        self.assertEqual(sum(g.min_tests for g in REQUIRED_GATES), 112)
        self.assertEqual(MIN_TOTAL_ATTACK_TESTS, 112)
        shadow = next(g for g in REQUIRED_GATES if g.gate_id == "no-return-shadow-graph")
        living = next(g for g in REQUIRED_GATES if g.gate_id == "living-synthetic-system")
        self.assertEqual(shadow.min_tests, 6)
        self.assertEqual(living.test_file, "tests/test_living_synthetic_system_v1.py")
        self.assertEqual(living.min_tests, 6)


if __name__ == "__main__":
    unittest.main()
