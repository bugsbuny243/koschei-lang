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
    AdversarialGate(
        "galaxy-learning-resistance",
        "tests/test_galaxy_adversarial_learning_v1.py",
        "rotating Nyr observations must not expose stable cross-session or cross-Veyra locators",
        6,
    ),
    AdversarialGate(
        "khar-failure-independence",
        "tests/test_khar_failure_independence_v1.py",
        "six logical axes must remain bound to six distinct failure roots and attestation domains",
        7,
    ),
    AdversarialGate(
        "galaxy-execution-gate",
        "tests/test_galaxy_execution_gate_v1.py",
        "critical execution requires living Matrix/Hara, exact Sathra and failure independence",
        5,
    ),
)

REQUIRED_GATES = V1_GATES + EXTRA_GATES
MIN_TOTAL_ATTACK_TESTS = 141


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


def evaluate_release_v2(
    *,
    candidate_id: str,
    runner: Runner,
    repo_root: str | Path = ".",
) -> AdversarialReportV2:
    cid = candidate_id.strip() if isinstance(candidate_id, str) else ""
    if not cid:
        raise ValueError("candidate_id must be non-empty")

    root = Path(repo_root)
    results: list[GateResultV2] = []
    for gate in REQUIRED_GATES:
        path = root / gate.test_file
        if not path.is_file():
            results.append(
                GateResultV2(
                    gate.gate_id,
                    gate.test_file,
                    False,
                    0,
                    gate.min_tests,
                    "required suite missing",
                )
            )
            continue
        try:
            passed, tests_run, detail = runner(gate.test_file)
            count = max(int(tests_run), 0)
            count_ok = count >= gate.min_tests
            ok = bool(passed) and count_ok
            if count == 0:
                detail = "suite executed zero tests"
            elif not count_ok:
                detail = (
                    f"test-count shrink detected: ran {count}, "
                    f"minimum {gate.min_tests}"
                )
            results.append(
                GateResultV2(
                    gate.gate_id,
                    gate.test_file,
                    ok,
                    count,
                    gate.min_tests,
                    str(detail),
                )
            )
        except Exception as exc:
            results.append(
                GateResultV2(
                    gate.gate_id,
                    gate.test_file,
                    False,
                    0,
                    gate.min_tests,
                    f"runner error: {type(exc).__name__}",
                )
            )

    frozen = tuple(results)
    total = sum(result.tests_run for result in frozen)
    ready = (
        len(frozen) == len(REQUIRED_GATES)
        and all(result.passed for result in frozen)
        and total >= MIN_TOTAL_ATTACK_TESTS
    )
    payload = json.dumps(
        {
            "candidate_id": cid,
            "minimum_total_tests": MIN_TOTAL_ATTACK_TESTS,
            "total_tests_run": total,
            "results": [
                {
                    "gate_id": result.gate_id,
                    "test_file": result.test_file,
                    "passed": result.passed,
                    "tests_run": result.tests_run,
                    "min_tests": result.min_tests,
                    "detail": result.detail,
                }
                for result in frozen
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return AdversarialReportV2(
        cid,
        ready,
        frozen,
        total,
        MIN_TOTAL_ATTACK_TESTS,
        hashlib.sha256(payload).hexdigest(),
    )
