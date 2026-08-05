"""Compare two independently verified Koschei native builds."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
