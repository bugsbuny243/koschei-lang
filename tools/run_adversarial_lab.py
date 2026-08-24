from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _junit_test_count(path: Path) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return 0
    raw = root.attrib.get("tests")
    if raw is not None:
        try:
            return max(int(raw), 0)
        except ValueError:
            return 0
    total = 0
    for suite in root.iter("testsuite"):
        try:
            total += max(int(suite.attrib.get("tests", "0")), 0)
        except ValueError:
            return 0
    return total


def _run_suite(test_file: str) -> tuple[bool, int, str]:
    """Run one required hostile-path suite and report its real collected count.

    Pytest is used deliberately because the living adversarial corpus contains
    both unittest.TestCase suites and pytest-style function suites. JUnit XML is
    the count oracle so output wording cannot silently change the anti-shrink
    budget.
    """

    with tempfile.TemporaryDirectory() as directory:
        report_path = Path(directory) / "pytest-report.xml"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                test_file,
                "-q",
                "--junitxml",
                str(report_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        tests_run = _junit_test_count(report_path)

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    tail = " | ".join(
        line.strip() for line in combined.splitlines()[-8:] if line.strip()
    )
    return proc.returncode == 0, tests_run, tail[:1000]


def _write_bootstrap_failure(
    json_out: str | None,
    candidate_id: str,
    exc: BaseException,
) -> None:
    payload = {
        "schema": "koschei/adversarial-lab-cli/v2",
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
    parser = argparse.ArgumentParser(
        description="Run Koschei Adversarial Lab v2 release gates"
    )
    parser.add_argument("--candidate", default="working-tree")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    try:
        from koschei.adversarial_lab_v2 import evaluate_release_v2

        report = evaluate_release_v2(
            candidate_id=args.candidate,
            runner=_run_suite,
            repo_root=REPO_ROOT,
        )
    except BaseException as exc:
        _write_bootstrap_failure(args.json_out, args.candidate, exc)
        return 3

    payload = {
        "schema": "koschei/adversarial-lab-cli/v2",
        "candidate_id": report.candidate_id,
        "commercial_ready": report.commercial_ready,
        "report_sha256": report.report_sha256,
        "minimum_total_tests": report.minimum_total_tests,
        "total_tests_run": report.total_tests_run,
        "gates": [
            {
                "gate_id": result.gate_id,
                "test_file": result.test_file,
                "passed": result.passed,
                "tests_run": result.tests_run,
                "min_tests": result.min_tests,
                "detail": result.detail,
            }
            for result in report.results
        ],
    }
    text = json.dumps(payload, sort_keys=True, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if report.commercial_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
