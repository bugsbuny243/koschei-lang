from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from koschei.adversarial_lab_v2 import MIN_TOTAL_ATTACK_TESTS, REQUIRED_GATES, evaluate_release_v2

class AdversarialLabV2Tests(unittest.TestCase):
    def root(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); r=Path(t.name)
        for g in REQUIRED_GATES:
            p=r/g.test_file; p.parent.mkdir(parents=True,exist_ok=True); p.write_text("# suite\n",encoding="utf-8")
        return r
    def runner(self,test_file):
        g=next(x for x in REQUIRED_GATES if x.test_file==test_file); return True,g.min_tests,"ok"
    def test_140_baseline(self):
        self.assertEqual(sum(g.min_tests for g in REQUIRED_GATES),140); self.assertEqual(MIN_TOTAL_ATTACK_TESTS,140)
    def test_distribution_shift_is_required(self):
        g=next(x for x in REQUIRED_GATES if x.gate_id=="distribution-shift-observer"); self.assertEqual(g.min_tests,5)
    def test_all_required_suites_are_commercial_ready(self):
        self.assertTrue(evaluate_release_v2(candidate_id="rc",repo_root=self.root(),runner=self.runner).commercial_ready)
    def test_missing_suite_fails_closed(self):
        r=self.root(); (r/"tests/test_distribution_shift_observer_v1.py").unlink(); self.assertFalse(evaluate_release_v2(candidate_id="rc",repo_root=r,runner=self.runner).commercial_ready)
    def test_digest_is_deterministic(self):
        r=self.root(); a=evaluate_release_v2(candidate_id="rc",repo_root=r,runner=self.runner); b=evaluate_release_v2(candidate_id="rc",repo_root=r,runner=self.runner); self.assertEqual(a.report_sha256,b.report_sha256)

if __name__=="__main__": unittest.main()
