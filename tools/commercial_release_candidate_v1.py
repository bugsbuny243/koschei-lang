#!/usr/bin/env python3
"""Build a reproducible Koschei Lang 0.10.0 commercial release candidate.

This tool prepares private deliverables for a store operator. It does NOT
publish to Polar, make payment URLs live, authenticate a publisher signature
or claim production safety. The exact commit's sealed local validation receipt
must pass and be release-eligible before producing any distributable files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Support direct invocation: python tools/commercial_release_candidate_v1.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from koschei.local_validation_v1 import (
    LocalValidationError,
    LocalValidationReceiptV1,
    LocalValidationStepV1,
)
from tools.pilot_security_gate_v1 import pilot_checks
from tools.polar_bundle_v1 import build_bundle, version

SCHEMA = "koschei.commercial-release-candidate/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class CommercialCandidateError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parent.parent,
    )
    value = completed.stdout.strip().lower()
    if not HEX40.fullmatch(value):
        raise CommercialCandidateError("invalid checkout commit")
    return value


def validate_receipt(path: Path, source_commit: str) -> LocalValidationReceiptV1:
    """Fully verify the internal receipt's self-consistency and exact head.

    The receipt digest is NOT a digital signature. External release
    authentication still requires a separately trusted release authority.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        steps = tuple(LocalValidationStepV1(
            **{**step, "command": tuple(step["command"])}
        ) for step in data.pop("steps"))
        receipt = LocalValidationReceiptV1(steps=steps, **data)
        receipt.require_for_release(source_commit)
    except (OSError, ValueError, TypeError, KeyError, LocalValidationError) as error:
        raise CommercialCandidateError(
            "exact-head full clean validated receipt is required"
        ) from error
    return receipt


def build_candidate(
    output_dir: Path,
    validation_receipt: Path,
    expected_version: str,
) -> dict:
    source_sha = _source_commit()
    if not HEX40.fullmatch(source_sha):
        raise CommercialCandidateError("invalid expected source SHA")
    if version() != expected_version:
        raise CommercialCandidateError(
            "release version mismatch: package metadata differs from requested version"
        )
    receipt = validate_receipt(validation_receipt, source_sha)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CommercialCandidateError("release output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="koschei-release-double-build-") as other:
        first_path = build_bundle(output_dir)
        second_path = build_bundle(Path(other))
        first = first_path.read_bytes()
        if first != second_path.read_bytes():
            raise CommercialCandidateError("independent bundle builds are not byte-identical")

    archive_sha = _sha256(first)
    pilot = pilot_checks(first_path, archive_sha)
    if not pilot["pilot_checks_passed"]:
        raise CommercialCandidateError("customer ZIP security examples did not pass")

    (output_dir / "SHA256SUMS").write_text(
        f"{archive_sha}  {first_path.name}\n", encoding="utf-8"
    )
    pilot_name = "customer-security-evidence.json"
    (output_dir / pilot_name).write_text(
        json.dumps(pilot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": SCHEMA,
        "version": expected_version,
        "source_commit": source_sha,
        "artifact_name": first_path.name,
        "artifact_sha256": archive_sha,
        "artifact_size_bytes": len(first),
        "reproducible_build": True,
        "pilot_evidence": pilot_name,
        "full_validation_receipt_sha256": _sha256(validation_receipt.read_bytes()),
        "full_validation_receipt_seal": receipt.digest,
        "full_validation_profile": receipt.profile,
        "full_validation_release_eligible": receipt.release_eligible,
        "publicly_published": False,
        "store_checkout_verified": False,
        "distributable_ready_for_operator_review": True,
        "attestation": "Local checksums are not a publisher signature or independent origin proof.",
    }
    (output_dir / "candidate-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--validation-receipt", required=True, type=Path)
    parser.add_argument("--expected-version", default="0.10.0")
    args = parser.parse_args(argv)
    try:
        manifest = build_candidate(
            args.output_dir.resolve(),
            args.validation_receipt.resolve(),
            args.expected_version,
        )
        print(
            f"COMMERCIAL CANDIDATE VERIFIED: {manifest['artifact_name']} "
            f"sha256={manifest['artifact_sha256']} "
            f"source={manifest['source_commit']}"
        )
        print("STORE PUBLISHED: false")
        return 0
    except (CommercialCandidateError, OSError, subprocess.SubprocessError) as error:
        print(f"commercial release candidate refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
