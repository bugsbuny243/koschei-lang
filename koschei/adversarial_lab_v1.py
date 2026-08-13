"""Koschei Adversarial Lab v1.

A release candidate is commercial-ready only if every required hostile-path
suite passes. Missing suites, empty suites, runner errors, partial success,
test-count shrinkage and attack-budget shrinkage all fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class AdversarialGate:
    gate_id: str
    test_file: str
    purpose: str
    min_tests: int


REQUIRED_GATES: tuple[AdversarialGate, ...] = (
    AdversarialGate("decoy-view", "tests/test_decoy_view_broker_v1.py", "unauthorized reads never reach canonical source", 7),
    AdversarialGate("decoy-attack", "tests/test_decoy_attack_simulation_v1.py", "replay/probing/cross-object decoy attacks fail closed", 5),
    AdversarialGate("read-auth", "tests/test_read_authorization_wave2.py", "epoch/object-bound read grants resist replay and tampering", 6),
    AdversarialGate("alias-rotation", "tests/test_epoch_alias_rotation_v1.py", "physical aliases rotate without changing canonical identity", 9),
    AdversarialGate("protected-graph", "tests/test_protected_graph_v1.py", "path fallback and decoy promotion remain forbidden", 5),
    AdversarialGate("entitlement", "tests/test_commercial_entitlement_v1.py", "commercial entitlement tampering fails closed", 5),
    AdversarialGate("activation", "tests/test_commercial_activation_v1.py", "seat/device/lease misuse fails closed", 8),
    AdversarialGate("private-distribution", "tests/test_private_distribution_v1.py", "artifact tamper, revocation and rollback attacks fail closed", 10),
    AdversarialGate("high-volume", "tests/test_high_volume_attack_profile_v1.py", "100k hostile reads, concurrency and stale correlation never reach canonical source", 3),
    AdversarialGate("compiler-integrity", "tests/test_compiler_integrity.py", "compiler integrity invariants remain enforced", 13),
    AdversarialGate("security-regressions", "tests/test_security_regressions.py", "known security regressions remain blocked", 13),
)

MIN_TOTAL_ATTACK_TESTS = 84


@dataclass(frozen=True, slots=True)
class GateResult:
    gate_id: str
    test_file: str
    passed: bool
    tests_run: int
    min_tests: int
    detail: str


@dataclass(frozen=True, slots=True)
class AdversarialReport:
    candidate_id: str
    commercial_ready: bool
    results: tuple[GateResult, ...]
    total_tests_run: int
    minimum_total_tests: int
    report_sha256: str


Runner = Callable[[str], tuple[bool, int, str]]


def _canonical_report_payload(candidate_id: str, results: tuple[GateResult, ...], total_tests_run: int) -> bytes:
    obj = {
        "schema": "koschei/adversarial-lab-report/v1",
        "candidate_id": candidate_id,
        "minimum_total_tests": MIN_TOTAL_ATTACK_TESTS,
        "total_tests_run": total_tests_run,
        "results": [
            {
                "gate_id": r.gate_id,
                "test_file": r.test_file,
                "passed": r.passed,
                "tests_run": r.tests_run,
                "min_tests": r.min_tests,
                "detail": r.detail,
            }
            for r in results
        ],
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def evaluate_release(*, candidate_id: str, runner: Runner, repo_root: str | Path = ".") -> AdversarialReport:
    candidate_id = candidate_id.strip() if isinstance(candidate_id, str) else ""
    if not candidate_id:
        raise ValueError("candidate_id must be non-empty")
    root = Path(repo_root)
    results: list[GateResult] = []
    for gate in REQUIRED_GATES:
        path = root / gate.test_file
        if not path.is_file():
            results.append(GateResult(gate.gate_id, gate.test_file, False, 0, gate.min_tests, "required suite missing"))
            continue
        try:
            passed, tests_run, detail = runner(gate.test_file)
            tests_run = max(int(tests_run), 0)
            count_ok = tests_run >= gate.min_tests
            ok = bool(passed) and count_ok
            if tests_run == 0:
                detail = "suite executed zero tests"
            elif not count_ok:
                detail = f"test-count shrink detected: ran {tests_run}, minimum {gate.min_tests}"
            results.append(GateResult(gate.gate_id, gate.test_file, ok, tests_run, gate.min_tests, str(detail)))
        except Exception as exc:  # fail closed by design
            results.append(GateResult(gate.gate_id, gate.test_file, False, 0, gate.min_tests, f"runner error: {type(exc).__name__}"))
    frozen = tuple(results)
    total_tests_run = sum(r.tests_run for r in frozen)
    commercial_ready = (
        len(frozen) == len(REQUIRED_GATES)
        and all(r.passed for r in frozen)
        and total_tests_run >= MIN_TOTAL_ATTACK_TESTS
    )
    digest = hashlib.sha256(_canonical_report_payload(candidate_id, frozen, total_tests_run)).hexdigest()
    return AdversarialReport(
        candidate_id,
        commercial_ready,
        frozen,
        total_tests_run,
        MIN_TOTAL_ATTACK_TESTS,
        digest,
    )
