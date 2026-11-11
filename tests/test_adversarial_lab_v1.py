from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.adversarial_lab_v1 import (
    MIN_TOTAL_ATTACK_TESTS,
    REQUIRED_GATES,
    evaluate_release,
)


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
        gate = next(gate for gate in REQUIRED_GATES if gate.test_file == test_file)
        return True, gate.min_tests, "ok"

    def test_all_gates_must_pass_for_commercial_ready(self):
        root = self._root_with_required_suites()
        report = evaluate_release(
            candidate_id="rc-1",
            repo_root=root,
            runner=self._baseline_runner,
        )
        self.assertTrue(report.commercial_ready)
        self.assertEqual(len(report.results), len(REQUIRED_GATES))
        self.assertEqual(report.total_tests_run, MIN_TOTAL_ATTACK_TESTS)
        self.assertEqual(report.minimum_total_tests, MIN_TOTAL_ATTACK_TESTS)
        self.assertEqual(len(report.report_sha256), 64)

    def test_one_failed_gate_blocks_release(self):
        root = self._root_with_required_suites()

        def runner(test_file: str):
            gate = next(gate for gate in REQUIRED_GATES if gate.test_file == test_file)
            if test_file.endswith("test_decoy_attack_simulation_v1.py"):
                return False, gate.min_tests, "attack escaped expected invariant"
            return True, gate.min_tests, "ok"

        report = evaluate_release(candidate_id="rc-2", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        self.assertEqual(sum(not result.passed for result in report.results), 1)

    def test_missing_suite_fails_closed_without_runner_call(self):
        root = self._root_with_required_suites()
        missing = root / REQUIRED_GATES[0].test_file
        missing.unlink()
        calls = []

        def runner(test_file: str):
            calls.append(test_file)
            gate = next(gate for gate in REQUIRED_GATES if gate.test_file == test_file)
            return True, gate.min_tests, "ok"

        report = evaluate_release(candidate_id="rc-3", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        first = next(
            result
            for result in report.results
            if result.gate_id == REQUIRED_GATES[0].gate_id
        )
        self.assertEqual(first.detail, "required suite missing")
        self.assertNotIn(REQUIRED_GATES[0].test_file, calls)

    def test_zero_test_suite_is_failure(self):
        root = self._root_with_required_suites()
        report = evaluate_release(
            candidate_id="rc-4",
            repo_root=root,
            runner=lambda _: (True, 0, "empty"),
        )
        self.assertFalse(report.commercial_ready)
        self.assertTrue(all(not result.passed for result in report.results))

    def test_runner_exception_fails_closed(self):
        root = self._root_with_required_suites()

        def runner(_):
            raise RuntimeError("boom")

        report = evaluate_release(candidate_id="rc-5", repo_root=root, runner=runner)
        self.assertFalse(report.commercial_ready)
        self.assertTrue(
            all(result.detail == "runner error: RuntimeError" for result in report.results)
        )

    def test_report_digest_is_deterministic(self):
        root = self._root_with_required_suites()
        first = evaluate_release(
            candidate_id="rc-6",
            repo_root=root,
            runner=self._baseline_runner,
        )
        second = evaluate_release(
            candidate_id="rc-6",
            repo_root=root,
            runner=self._baseline_runner,
        )
        self.assertEqual(first.report_sha256, second.report_sha256)

    def test_per_gate_test_count_shrink_blocks_release(self):
        root = self._root_with_required_suites()
        target = REQUIRED_GATES[0]

        def runner(test_file: str):
            gate = next(gate for gate in REQUIRED_GATES if gate.test_file == test_file)
            count = gate.min_tests - 1 if gate.gate_id == target.gate_id else gate.min_tests
            return True, count, "runner green"

        report = evaluate_release(
            candidate_id="rc-shrink",
            repo_root=root,
            runner=runner,
        )
        self.assertFalse(report.commercial_ready)
        result = next(item for item in report.results if item.gate_id == target.gate_id)
        self.assertFalse(result.passed)
        self.assertIn("test-count shrink detected", result.detail)

    def test_living_attack_budget_is_ratcheted_to_118(self):
        self.assertEqual(sum(gate.min_tests for gate in REQUIRED_GATES), 118)
        self.assertEqual(MIN_TOTAL_ATTACK_TESTS, 118)

        expected_floors = {
            "decoy-view": 15,
            "decoy-attack": 5,
            "read-auth": 10,
            "alias-rotation": 9,
            "protected-graph": 7,
            "entitlement": 5,
            "activation": 13,
            "private-distribution": 13,
            "high-volume": 3,
            "million-probe": 3,
            "transport-shaping": 6,
            "classifier-resistance": 3,
            "compiler-integrity": 13,
            "security-regressions": 13,
        }
        self.assertEqual(
            {gate.gate_id: gate.min_tests for gate in REQUIRED_GATES},
            expected_floors,
        )


if __name__ == "__main__":
    unittest.main()
