from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from koschei.adversarial_lab_v1 import evaluate_release


def _run_suite(test_file: str) -> tuple[bool, int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", Path(test_file).name, "-v"],
        text=True,
        capture_output=True,
        check=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"Ran\s+(\d+)\s+tests?", combined)
    tests_run = int(match.group(1)) if match else 0
    tail = " | ".join(line.strip() for line in combined.splitlines()[-4:] if line.strip())
    return proc.returncode == 0, tests_run, tail[:500]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Koschei Adversarial Lab release gates")
    parser.add_argument("--candidate", default="working-tree")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    report = evaluate_release(candidate_id=args.candidate, runner=_run_suite, repo_root=".")
    payload = {
        "schema": "koschei/adversarial-lab-cli/v1",
        "candidate_id": report.candidate_id,
        "commercial_ready": report.commercial_ready,
        "report_sha256": report.report_sha256,
        "gates": [
            {
                "gate_id": r.gate_id,
                "test_file": r.test_file,
                "passed": r.passed,
                "tests_run": r.tests_run,
                "detail": r.detail,
            }
            for r in report.results
        ],
    }
    text = json.dumps(payload, sort_keys=True, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if report.commercial_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
