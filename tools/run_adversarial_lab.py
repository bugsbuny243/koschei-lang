from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_suite(test_file: str) -> tuple[bool, int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", Path(test_file).name, "-v"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"Ran\s+(\d+)\s+tests?", combined)
    tests_run = int(match.group(1)) if match else 0
    tail = " | ".join(line.strip() for line in combined.splitlines()[-6:] if line.strip())
    return proc.returncode == 0, tests_run, tail[:800]


def _write_bootstrap_failure(json_out: str | None, candidate_id: str, exc: BaseException) -> None:
    payload = {
        "schema": "koschei/adversarial-lab-cli/v1",
        "candidate_id": candidate_id,
        "commercial_ready": False,
        "report_sha256": None,
        "bootstrap_error": f"{type(exc).__name__}: {exc}",
        "minimum_total_tests": None,
        "total_tests_run": 0,
        "gates": [],
    }
    text = json.dumps(payload, sort_keys=True, indent=2)
    print(text, file=sys.stderr)
    if json_out:
        Path(json_out).write_text(text + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Koschei Adversarial Lab release gates")
    parser.add_argument("--candidate", default="working-tree")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    try:
        from koschei.adversarial_lab_v1 import evaluate_release

        report = evaluate_release(candidate_id=args.candidate, runner=_run_suite, repo_root=REPO_ROOT)
    except BaseException as exc:
        _write_bootstrap_failure(args.json_out, args.candidate, exc)
        return 3

    payload = {
        "schema": "koschei/adversarial-lab-cli/v1",
        "candidate_id": report.candidate_id,
        "commercial_ready": report.commercial_ready,
        "report_sha256": report.report_sha256,
        "minimum_total_tests": report.minimum_total_tests,
        "total_tests_run": report.total_tests_run,
        "gates": [
            {
                "gate_id": r.gate_id,
                "test_file": r.test_file,
                "passed": r.passed,
                "tests_run": r.tests_run,
                "min_tests": r.min_tests,
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
