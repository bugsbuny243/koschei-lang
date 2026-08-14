from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

from koschei.adversarial_lab_v1 import AdversarialGate, REQUIRED_GATES as V1_GATES

EXTRA_GATES: tuple[AdversarialGate, ...] = (
    AdversarialGate(
        "distribution-shift-observer",
        "tests/test_distribution_shift_observer_v1.py",
        "sampling and epoch-schedule variation must not create object-label signal",
        5,
    ),
)
REQUIRED_GATES = V1_GATES + EXTRA_GATES
MIN_TOTAL_ATTACK_TESTS = 140

@dataclass(frozen=True, slots=True)
class GateResultV2:
    gate_id: str
    test_file: str
    passed: bool
    tests_run: int
    min_tests: int
    detail: str

@dataclass(frozen=True, slots=True)
class AdversarialReportV2:
    candidate_id: str
    commercial_ready: bool
    results: tuple[GateResultV2, ...]
    total_tests_run: int
    minimum_total_tests: int
    report_sha256: str

Runner = Callable[[str], tuple[bool, int, str]]

def evaluate_release_v2(*, candidate_id: str, runner: Runner, repo_root: str | Path = ".") -> AdversarialReportV2:
    cid = candidate_id.strip() if isinstance(candidate_id, str) else ""
    if not cid:
        raise ValueError("candidate_id must be non-empty")
    root = Path(repo_root)
    results: list[GateResultV2] = []
    for gate in REQUIRED_GATES:
        path = root / gate.test_file
        if not path.is_file():
            results.append(GateResultV2(gate.gate_id, gate.test_file, False, 0, gate.min_tests, "required suite missing"))
            continue
        try:
            passed, tests_run, detail = runner(gate.test_file)
            count = max(int(tests_run), 0)
            ok = bool(passed) and count >= gate.min_tests
            if count == 0:
                detail = "suite executed zero tests"
            elif count < gate.min_tests:
                detail = f"test-count shrink detected: ran {count}, minimum {gate.min_tests}"
            results.append(GateResultV2(gate.gate_id, gate.test_file, ok, count, gate.min_tests, str(detail)))
        except Exception as exc:
            results.append(GateResultV2(gate.gate_id, gate.test_file, False, 0, gate.min_tests, f"runner error: {type(exc).__name__}"))
    frozen = tuple(results)
    total = sum(r.tests_run for r in frozen)
    ready = all(r.passed for r in frozen) and total >= MIN_TOTAL_ATTACK_TESTS
    payload = json.dumps({"candidate_id": cid, "minimum_total_tests": MIN_TOTAL_ATTACK_TESTS, "total_tests_run": total, "results": [r.__dict__ if hasattr(r, "__dict__") else {"gate_id": r.gate_id, "test_file": r.test_file, "passed": r.passed, "tests_run": r.tests_run, "min_tests": r.min_tests, "detail": r.detail} for r in frozen]}, sort_keys=True, separators=(",", ":")).encode()
    return AdversarialReportV2(cid, ready, frozen, total, MIN_TOTAL_ATTACK_TESTS, hashlib.sha256(payload).hexdigest())
