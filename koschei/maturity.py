"""Deterministic evidence gate for Koschei language maturity claims."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MaturityTarget = Literal["incubation", "reference", "production"]

SUPPORTED_CHECKS = frozenset(
    {
        "compiler_tests",
        "repository_truth",
        "capability_security",
        "syntax_stability",
        "type_system_stability",
        "runtime_abi_stability",
        "package_integrity",
        "reproducible_builds",
        "interpreter_native_parity",
        "foreign_boundary_parity",
        "fuzzing",
        "adversarial_capability_tests",
        "real_programs",
        "rollback_reference_component",
        "owner_approval",
    }
)

TARGET_REQUIREMENTS: dict[MaturityTarget, tuple[str, ...]] = {
    "incubation": (
        "compiler_tests",
        "repository_truth",
        "capability_security",
    ),
    "reference": (
        "compiler_tests",
        "repository_truth",
        "capability_security",
        "syntax_stability",
        "type_system_stability",
        "package_integrity",
        "reproducible_builds",
        "interpreter_native_parity",
        "real_programs",
    ),
    "production": (
        "compiler_tests",
        "repository_truth",
        "capability_security",
        "syntax_stability",
        "type_system_stability",
        "runtime_abi_stability",
        "package_integrity",
        "reproducible_builds",
        "interpreter_native_parity",
        "foreign_boundary_parity",
        "fuzzing",
        "adversarial_capability_tests",
        "real_programs",
        "rollback_reference_component",
        "owner_approval",
    ),
}


@dataclass(frozen=True)
class MaturityEvidence:
    checks: dict[str, bool]


@dataclass(frozen=True)
class MaturityReport:
    target: MaturityTarget
    ready: bool
    evidence_digest: str
    required_checks: tuple[str, ...]
    passed_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "koschei.maturity-report.v1",
            "target": self.target,
            "ready": self.ready,
            "evidence_digest": self.evidence_digest,
            "required_checks": list(self.required_checks),
            "passed_checks": list(self.passed_checks),
            "missing_checks": list(self.missing_checks),
            "production_integration_allowed": self.target == "production" and self.ready,
        }


def load_maturity_evidence(path: str | Path) -> MaturityEvidence:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("maturity evidence is not valid JSON") from error

    if not isinstance(payload, dict):
        raise ValueError("maturity evidence must be a JSON object")
    if set(payload) != {"schema_version", "checks"}:
        raise ValueError("maturity evidence contains unsupported top-level fields")
    if payload["schema_version"] != "koschei.maturity-evidence.v1":
        raise ValueError("unsupported maturity evidence schema")

    checks = payload["checks"]
    if not isinstance(checks, dict):
        raise ValueError("maturity evidence checks must be an object")
    unknown = sorted(set(checks) - SUPPORTED_CHECKS)
    if unknown:
        raise ValueError("unsupported maturity checks: " + ", ".join(unknown))
    invalid = sorted(name for name, value in checks.items() if type(value) is not bool)
    if invalid:
        raise ValueError("maturity checks must be booleans: " + ", ".join(invalid))

    return MaturityEvidence(checks=dict(checks))


def evaluate_maturity(
    evidence: MaturityEvidence,
    target: MaturityTarget,
) -> MaturityReport:
    required = TARGET_REQUIREMENTS[target]
    passed = tuple(name for name in required if evidence.checks.get(name) is True)
    missing = tuple(name for name in required if evidence.checks.get(name) is not True)
    digest = hashlib.sha256(_canonical_evidence(evidence).encode("utf-8")).hexdigest()
    return MaturityReport(
        target=target,
        ready=not missing,
        evidence_digest=digest,
        required_checks=required,
        passed_checks=passed,
        missing_checks=missing,
    )


def render_maturity_report(report: MaturityReport) -> str:
    return json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n"


def _canonical_evidence(evidence: MaturityEvidence) -> str:
    payload = {
        "schema_version": "koschei.maturity-evidence.v1",
        "checks": evidence.checks,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
