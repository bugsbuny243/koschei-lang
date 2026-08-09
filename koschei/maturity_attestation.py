"""Build attested maturity evidence from verified release and CI artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .maturity import (
    MaturityEvidence,
    PROTECTED_ATTESTED_CHECKS,
    canonical_v1_payload,
)
from .release_proof import ReleaseProof

_SCHEMA = "koschei.maturity-evidence.v2"
_MAX_CI_ARTIFACT_BYTES = 16 * 1024 * 1024
_MAX_CI_REPORT_BYTES = 2 * 1024 * 1024


class MaturityAttestationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def build_attested_maturity_evidence(
    base: MaturityEvidence,
    proof: ReleaseProof,
    *,
    ci_artifact_path: str | Path,
    ci_head_sha: str,
) -> dict[str, object]:
    if base.schema_version != "koschei.maturity-evidence.v1" or base.canonical_payload is not None:
        raise MaturityAttestationError("KS1940", "base evidence must use schema v1")
    if any(base.checks.get(name) is True for name in PROTECTED_ATTESTED_CHECKS):
        raise MaturityAttestationError(
            "KS1940",
            "base evidence must not self-assert protected reproducibility checks",
        )
    _verify_release_proof_identity(proof)
    _require_commit_sha(ci_head_sha)

    artifact_path = Path(ci_artifact_path)
    artifact_raw = artifact_path.read_bytes()
    if not artifact_raw:
        raise MaturityAttestationError("KS1941", "CI artifact is empty")
    if len(artifact_raw) > _MAX_CI_ARTIFACT_BYTES:
        raise MaturityAttestationError("KS1941", "CI artifact exceeds the size limit")
    report_raw = _extract_truth_report(artifact_raw)
    observation = _parse_truth_report(report_raw)

    checks = dict(base.checks)
    checks["package_integrity"] = True
    checks["reproducible_builds"] = True
    manual_payload = canonical_v1_payload(base)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA,
        "checks": checks,
        "derived_checks": ["package_integrity", "reproducible_builds"],
        "manual_evidence_digest": _digest(manual_payload),
        "release_proof_digest": proof.proof_digest,
        "release_artifact_sha256": proof.release_artifact_sha256,
        "module_lock_digest": proof.module_lock_digest,
        "ci_artifact_sha256": hashlib.sha256(artifact_raw).hexdigest(),
        "ci_head_sha": ci_head_sha,
        "ci_report_sha256": hashlib.sha256(report_raw).hexdigest(),
        "ci_test_artifact_sha256": observation["test_artifact_sha256"],
        "ci_test_count": observation["test_count"],
        "ci_warning_count": observation["warning_count"],
        "ci_repository_truth_observed": True,
        "ci_sealed_mir_observed": True,
        "ci_capability_security_observed": True,
    }
    return {**payload, "attestation_digest": _digest(payload)}


def write_attested_maturity_evidence(
    payload: dict[str, object],
    destination: str | Path,
) -> None:
    path = Path(destination)
    if path.exists():
        raise MaturityAttestationError(
            "KS1943",
            f"attested maturity evidence already exists: {path}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _verify_release_proof_identity(proof: ReleaseProof) -> None:
    payload = proof.to_dict()
    claimed = payload.pop("proof_digest")
    if claimed != _digest(payload):
        raise MaturityAttestationError("KS1940", "release proof digest does not match contents")
    if proof.state != "verified_reproducible_release_candidate":
        raise MaturityAttestationError("KS1940", "release proof state is invalid")
    if proof.authority != "release_candidate_evidence_only":
        raise MaturityAttestationError("KS1940", "release proof authority is invalid")
    if not proof.byte_reproducible:
        raise MaturityAttestationError("KS1940", "release proof is not byte reproducible")
    if proof.release_artifact_sha256 != proof.witness_artifact_sha256:
        raise MaturityAttestationError("KS1940", "release and witness artifact digests differ")
    if not proof.owner_approval_required:
        raise MaturityAttestationError("KS1940", "release proof must preserve owner approval")
    if proof.automatic_publish_allowed or proof.package_registry_write_allowed:
        raise MaturityAttestationError("KS1940", "release proof exceeds evidence-only authority")
    if proof.production_integration_allowed:
        raise MaturityAttestationError("KS1940", "release proof must not authorize production")


def _extract_truth_report(raw: bytes) -> bytes:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        raise MaturityAttestationError("KS1941", "CI artifact is not a valid ZIP") from error
    with archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        for item in files:
            name = item.filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise MaturityAttestationError("KS1941", "CI artifact contains an unsafe path")
        reports = [item for item in files if PurePosixPath(item.filename).name == "verify-report.txt"]
        if len(reports) != 1:
            raise MaturityAttestationError(
                "KS1941",
                "CI artifact must contain exactly one verify-report.txt",
            )
        report = reports[0]
        if report.file_size <= 0 or report.file_size > _MAX_CI_REPORT_BYTES:
            raise MaturityAttestationError("KS1941", "CI verify report has an invalid size")
        return archive.read(report)


def _parse_truth_report(raw: bytes) -> dict[str, object]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MaturityAttestationError("KS1942", "CI verify report must be UTF-8") from error
    if not text.startswith("Koschei verify — Koschei "):
        raise MaturityAttestationError("KS1942", "CI verify report header is invalid")

    tests = re.search(
        r"PASS\s+Ran\s+(\d+)\s+tests\s+—\s+ARTIFACT SHA256:\s*([a-f0-9]{64})",
        text,
    )
    if tests is None or int(tests.group(1)) <= 0:
        raise MaturityAttestationError("KS1942", "CI verify report has no passing test suite")
    if "PASS  check and backend input share one sealed MIR fingerprint" not in text:
        raise MaturityAttestationError("KS1942", "CI verify report lacks sealed MIR proof")
    if re.search(r"PASS\s+examples/capability\.ks", text) is None:
        raise MaturityAttestationError("KS1942", "CI verify report lacks capability example")
    if re.search(
        r"PASS\s+examples/supply_chain/main\.ks\s+—\s+correctly rejected with KS2401",
        text,
    ) is None:
        raise MaturityAttestationError("KS1942", "CI verify report lacks supply-chain rejection")
    summary = re.search(r"(\d+)\s+warning\(s\),\s+no failures\.", text)
    if summary is None:
        raise MaturityAttestationError("KS1942", "CI verify report does not prove no failures")
    return {
        "test_count": int(tests.group(1)),
        "test_artifact_sha256": tests.group(2),
        "warning_count": int(summary.group(1)),
    }


def _require_commit_sha(value: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise MaturityAttestationError(
            "KS1940",
            "CI head SHA must be a 40-character lowercase Git commit SHA",
        )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
