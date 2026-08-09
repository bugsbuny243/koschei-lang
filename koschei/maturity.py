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
PROTECTED_ATTESTED_CHECKS = frozenset(
    {"package_integrity", "reproducible_builds", "interpreter_native_parity"}
)
REFERENCE_ATTESTED_CHECKS = frozenset(
    {
        "compiler_tests",
        "repository_truth",
        "capability_security",
        "package_integrity",
        "reproducible_builds",
        "interpreter_native_parity",
    }
)
_ATTESTED_FIELDS_V23 = {
    "schema_version",
    "checks",
    "derived_checks",
    "manual_evidence_digest",
    "release_proof_digest",
    "release_artifact_sha256",
    "module_lock_digest",
    "ci_artifact_sha256",
    "ci_head_sha",
    "ci_report_sha256",
    "ci_test_artifact_sha256",
    "ci_test_count",
    "ci_warning_count",
    "ci_repository_truth_observed",
    "ci_sealed_mir_observed",
    "ci_capability_security_observed",
    "attestation_digest",
}
_ATTESTED_FIELDS_V4 = _ATTESTED_FIELDS_V23 | {
    "ci_parity_evidence_sha256",
    "ci_parity_case_count",
    "ci_interpreter_native_parity_observed",
}
_V2_DERIVED = ["package_integrity", "reproducible_builds"]
_V3_DERIVED = [
    "capability_security",
    "compiler_tests",
    "package_integrity",
    "repository_truth",
    "reproducible_builds",
]
_V4_DERIVED = [
    "capability_security",
    "compiler_tests",
    "interpreter_native_parity",
    "package_integrity",
    "repository_truth",
    "reproducible_builds",
]

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
    schema_version: str = "koschei.maturity-evidence.v1"
    canonical_payload: dict[str, object] | None = None


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
    schema = payload.get("schema_version")
    if schema == "koschei.maturity-evidence.v1":
        return _load_v1(payload)
    if schema == "koschei.maturity-evidence.v2":
        return _load_attested(payload, schema, _V2_DERIVED, _ATTESTED_FIELDS_V23)
    if schema == "koschei.maturity-evidence.v3":
        return _load_attested(payload, schema, _V3_DERIVED, _ATTESTED_FIELDS_V23)
    if schema == "koschei.maturity-evidence.v4":
        return _load_attested(payload, schema, _V4_DERIVED, _ATTESTED_FIELDS_V4)
    raise ValueError("unsupported maturity evidence schema")


def evaluate_maturity(
    evidence: MaturityEvidence,
    target: MaturityTarget,
    *,
    attestation_verified: bool = False,
) -> MaturityReport:
    required = TARGET_REQUIREMENTS[target]
    passed = tuple(
        name
        for name in required
        if _trusted_check(evidence, target, name, attestation_verified=attestation_verified)
    )
    missing = tuple(name for name in required if name not in passed)
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


def canonical_v1_payload(evidence: MaturityEvidence) -> dict[str, object]:
    return {
        "schema_version": "koschei.maturity-evidence.v1",
        "checks": evidence.checks,
    }


def _trusted_check(
    evidence: MaturityEvidence,
    target: MaturityTarget,
    name: str,
    *,
    attestation_verified: bool,
) -> bool:
    if evidence.checks.get(name) is not True:
        return False
    if target != "incubation" and name in REFERENCE_ATTESTED_CHECKS:
        return evidence.schema_version == "koschei.maturity-evidence.v4" and attestation_verified
    return True


def _load_v1(payload: dict[str, object]) -> MaturityEvidence:
    if set(payload) != {"schema_version", "checks"}:
        raise ValueError("maturity evidence contains unsupported top-level fields")
    checks = _validate_checks(payload["checks"])
    forbidden = sorted(
        name for name in PROTECTED_ATTESTED_CHECKS if checks.get(name) is True
    )
    if forbidden:
        raise ValueError(
            "protected maturity checks require attested v2, v3, or v4 evidence: "
            + ", ".join(forbidden)
        )
    return MaturityEvidence(checks=checks)


def _load_attested(
    payload: dict[str, object],
    schema: str,
    expected_derived: list[str],
    expected_fields: set[str],
) -> MaturityEvidence:
    if set(payload) != expected_fields:
        raise ValueError("attested maturity evidence contains unsupported fields")
    checks = _validate_checks(payload["checks"])
    if payload["derived_checks"] != expected_derived:
        raise ValueError("attested maturity derived checks are not canonical")
    if any(checks.get(name) is not True for name in expected_derived):
        raise ValueError("attested maturity evidence must prove every derived check")

    digest_fields = [
        "manual_evidence_digest",
        "release_proof_digest",
        "release_artifact_sha256",
        "module_lock_digest",
        "ci_artifact_sha256",
        "ci_report_sha256",
        "ci_test_artifact_sha256",
        "attestation_digest",
    ]
    if schema == "koschei.maturity-evidence.v4":
        digest_fields.append("ci_parity_evidence_sha256")
    for field in digest_fields:
        if not _is_digest(payload[field]):
            raise ValueError(f"{field} must be SHA-256")

    head_sha = payload["ci_head_sha"]
    if not isinstance(head_sha, str) or len(head_sha) != 40 or any(
        character not in "0123456789abcdef" for character in head_sha
    ):
        raise ValueError("ci_head_sha must be a 40-character lowercase Git commit SHA")
    for field in ("ci_test_count", "ci_warning_count"):
        value = payload[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
    if payload["ci_test_count"] == 0:
        raise ValueError("ci_test_count must be positive")

    required_true = [
        "ci_repository_truth_observed",
        "ci_sealed_mir_observed",
        "ci_capability_security_observed",
    ]
    if schema == "koschei.maturity-evidence.v4":
        parity_count = payload["ci_parity_case_count"]
        if not isinstance(parity_count, int) or isinstance(parity_count, bool) or parity_count < 5:
            raise ValueError("ci_parity_case_count must be an integer of at least 5")
        required_true.append("ci_interpreter_native_parity_observed")
    for field in required_true:
        if payload[field] is not True:
            raise ValueError(f"{field} must be true")

    unsigned = dict(payload)
    claimed = unsigned.pop("attestation_digest")
    if claimed != _digest(unsigned):
        raise ValueError("attested maturity evidence digest does not match contents")
    return MaturityEvidence(
        checks=checks,
        schema_version=schema,
        canonical_payload=dict(payload),
    )


def _validate_checks(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise ValueError("maturity evidence checks must be an object")
    unknown = sorted(set(raw) - SUPPORTED_CHECKS)
    if unknown:
        raise ValueError("unsupported maturity checks: " + ", ".join(unknown))
    invalid = sorted(name for name, value in raw.items() if type(value) is not bool)
    if invalid:
        raise ValueError("maturity checks must be booleans: " + ", ".join(invalid))
    return dict(raw)


def _canonical_evidence(evidence: MaturityEvidence) -> str:
    payload = evidence.canonical_payload or canonical_v1_payload(evidence)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
