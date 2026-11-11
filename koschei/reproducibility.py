"""Compare and verify independently attested Koschei native builds."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .build_manifest import NativeBuildManifest

_SCHEMA = "koschei.reproducibility-report.v1"
_INPUT_FIELDS = (
    "module_lock_digest",
    "mir_version",
    "mir_fingerprint",
    "compiler_version",
    "backend",
    "backend_toolchain",
)
_REPORT_FIELDS = {
    "schema_version",
    "status",
    "comparable",
    "byte_reproducible",
    "input_mismatches",
    "artifact_name_match",
    "left_manifest_digest",
    "right_manifest_digest",
    "left_artifact_sha256",
    "right_artifact_sha256",
    "shared_input_digest",
    "report_digest",
}
_STATUSES = {"byte_identical", "artifact_mismatch", "not_comparable"}


class ReproducibilityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ReproducibilityReport:
    status: str
    comparable: bool
    byte_reproducible: bool
    input_mismatches: tuple[str, ...]
    artifact_name_match: bool
    left_manifest_digest: str
    right_manifest_digest: str
    left_artifact_sha256: str
    right_artifact_sha256: str
    shared_input_digest: str | None
    report_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "status": self.status,
            "comparable": self.comparable,
            "byte_reproducible": self.byte_reproducible,
            "input_mismatches": list(self.input_mismatches),
            "artifact_name_match": self.artifact_name_match,
            "left_manifest_digest": self.left_manifest_digest,
            "right_manifest_digest": self.right_manifest_digest,
            "left_artifact_sha256": self.left_artifact_sha256,
            "right_artifact_sha256": self.right_artifact_sha256,
            "shared_input_digest": self.shared_input_digest,
            "report_digest": self.report_digest,
        }


def compare_verified_builds(
    left: NativeBuildManifest,
    right: NativeBuildManifest,
) -> ReproducibilityReport:
    mismatches = tuple(
        field for field in _INPUT_FIELDS if getattr(left, field) != getattr(right, field)
    )
    comparable = not mismatches
    byte_reproducible = comparable and left.artifact_sha256 == right.artifact_sha256
    if not comparable:
        status = "not_comparable"
        shared_input_digest = None
    elif byte_reproducible:
        status = "byte_identical"
        shared_input_digest = _input_digest(left)
    else:
        status = "artifact_mismatch"
        shared_input_digest = _input_digest(left)

    payload = {
        "schema_version": _SCHEMA,
        "status": status,
        "comparable": comparable,
        "byte_reproducible": byte_reproducible,
        "input_mismatches": list(mismatches),
        "artifact_name_match": left.artifact_name == right.artifact_name,
        "left_manifest_digest": left.manifest_digest,
        "right_manifest_digest": right.manifest_digest,
        "left_artifact_sha256": left.artifact_sha256,
        "right_artifact_sha256": right.artifact_sha256,
        "shared_input_digest": shared_input_digest,
    }
    return ReproducibilityReport(
        status=status,
        comparable=comparable,
        byte_reproducible=byte_reproducible,
        input_mismatches=mismatches,
        artifact_name_match=left.artifact_name == right.artifact_name,
        left_manifest_digest=left.manifest_digest,
        right_manifest_digest=right.manifest_digest,
        left_artifact_sha256=left.artifact_sha256,
        right_artifact_sha256=right.artifact_sha256,
        shared_input_digest=shared_input_digest,
        report_digest=_digest(payload),
    )


def load_reproducibility_report(path: str | Path) -> ReproducibilityReport:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReproducibilityError(
            "KS1924",
            "reproducibility report is not valid JSON",
        ) from error
    return _parse_report(payload)


def verify_reproducibility_report(
    report: ReproducibilityReport,
    left: NativeBuildManifest,
    right: NativeBuildManifest,
) -> ReproducibilityReport:
    verified = _parse_report(report.to_dict())
    expected = compare_verified_builds(left, right)
    if verified.to_dict() != expected.to_dict():
        raise ReproducibilityError(
            "KS1925",
            "reproducibility report does not match the supplied verified builds",
        )
    return verified


def write_reproducibility_report(
    report: ReproducibilityReport,
    destination: str | Path,
) -> None:
    path = Path(destination)
    if path.exists():
        raise ReproducibilityError(
            "KS1923",
            f"reproducibility report already exists: {path}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _parse_report(payload: Any) -> ReproducibilityReport:
    if not isinstance(payload, dict):
        raise ReproducibilityError("KS1924", "reproducibility report must be an object")
    if set(payload) != _REPORT_FIELDS:
        raise ReproducibilityError(
            "KS1924",
            "reproducibility report contains unsupported fields",
        )
    if payload["schema_version"] != _SCHEMA:
        raise ReproducibilityError("KS1924", "unsupported reproducibility report schema")

    status = payload["status"]
    if not isinstance(status, str) or status not in _STATUSES:
        raise ReproducibilityError("KS1924", "invalid reproducibility status")
    comparable = _bool(payload["comparable"], "comparable")
    byte_reproducible = _bool(payload["byte_reproducible"], "byte_reproducible")
    artifact_name_match = _bool(payload["artifact_name_match"], "artifact_name_match")

    raw_mismatches = payload["input_mismatches"]
    if not isinstance(raw_mismatches, list) or any(
        not isinstance(item, str) for item in raw_mismatches
    ):
        raise ReproducibilityError("KS1924", "input_mismatches must be a string array")
    mismatches = tuple(raw_mismatches)
    if len(mismatches) != len(set(mismatches)):
        raise ReproducibilityError("KS1924", "input_mismatches contains duplicates")
    if any(item not in _INPUT_FIELDS for item in mismatches):
        raise ReproducibilityError("KS1924", "input_mismatches contains unknown fields")
    expected_order = tuple(field for field in _INPUT_FIELDS if field in mismatches)
    if mismatches != expected_order:
        raise ReproducibilityError("KS1924", "input_mismatches is not canonical")

    left_manifest_digest = _digest_field(
        payload["left_manifest_digest"],
        "left_manifest_digest",
    )
    right_manifest_digest = _digest_field(
        payload["right_manifest_digest"],
        "right_manifest_digest",
    )
    left_artifact_sha256 = _digest_field(
        payload["left_artifact_sha256"],
        "left_artifact_sha256",
    )
    right_artifact_sha256 = _digest_field(
        payload["right_artifact_sha256"],
        "right_artifact_sha256",
    )
    shared_raw = payload["shared_input_digest"]
    if shared_raw is not None and not _is_digest(shared_raw):
        raise ReproducibilityError("KS1924", "shared_input_digest must be SHA-256 or null")
    shared_input_digest = shared_raw
    report_digest = _digest_field(payload["report_digest"], "report_digest")

    if status == "byte_identical":
        valid_state = comparable and byte_reproducible and not mismatches
        valid_state = valid_state and shared_input_digest is not None
        valid_state = valid_state and left_artifact_sha256 == right_artifact_sha256
    elif status == "artifact_mismatch":
        valid_state = comparable and not byte_reproducible and not mismatches
        valid_state = valid_state and shared_input_digest is not None
        valid_state = valid_state and left_artifact_sha256 != right_artifact_sha256
    else:
        valid_state = not comparable and not byte_reproducible and bool(mismatches)
        valid_state = valid_state and shared_input_digest is None
    if not valid_state:
        raise ReproducibilityError(
            "KS1924",
            "reproducibility report state is internally inconsistent",
        )

    unsigned = dict(payload)
    unsigned.pop("report_digest")
    if report_digest != _digest(unsigned):
        raise ReproducibilityError(
            "KS1924",
            "reproducibility report digest does not match contents",
        )

    return ReproducibilityReport(
        status=status,
        comparable=comparable,
        byte_reproducible=byte_reproducible,
        input_mismatches=mismatches,
        artifact_name_match=artifact_name_match,
        left_manifest_digest=left_manifest_digest,
        right_manifest_digest=right_manifest_digest,
        left_artifact_sha256=left_artifact_sha256,
        right_artifact_sha256=right_artifact_sha256,
        shared_input_digest=shared_input_digest,
        report_digest=report_digest,
    )


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReproducibilityError("KS1924", f"{field} must be boolean")
    return value


def _digest_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not _is_digest(value):
        raise ReproducibilityError("KS1924", f"{field} must be SHA-256")
    return value


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _input_digest(manifest: NativeBuildManifest) -> str:
    return _digest({field: getattr(manifest, field) for field in _INPUT_FIELDS})


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
