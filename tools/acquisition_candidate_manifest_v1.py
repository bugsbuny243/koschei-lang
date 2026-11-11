#!/usr/bin/env python3
"""Create a fail-closed acquisition-candidate evidence manifest.

The manifest binds one immutable Git commit, package version, release inputs and
already-produced evidence. Validation, SBOM and reproducibility receipts are
verified semantically before their bytes are admitted to the candidate record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

from koschei.local_validation_v1 import (
    LocalValidationReceiptV1,
    LocalValidationStepV1,
)

REPOSITORY = "bugsbuny243/koschei-lang"
SCHEMA = "koschei.acquisition-candidate/v1"
SBOM_SCHEMA = "koschei.acquisition-sbom/v1"
REPRO_SCHEMA = "koschei.reproducible-artifact-receipt/v1"
RELEASE_INPUTS = (
    "Dockerfile.production",
    "production-container-lock.json",
    "production-build-bootstrap.txt",
    "production-build-requirements.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    value = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("candidate commit must be a full lowercase SHA-1 identity")
    return value


def require_clean_tree(root: Path) -> None:
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    ).strip()
    if dirty:
        raise ValueError("acquisition candidate manifest refuses a dirty working tree")


def project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml project.version is missing")
    return version


def evidence_record(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"required acquisition evidence is missing: {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"required acquisition evidence is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _validation_receipt(path: Path, commit: str) -> None:
    payload = _json_object(path, "validation receipt")
    try:
        steps = tuple(
            LocalValidationStepV1(**step) for step in payload.get("steps", ())
        )
        receipt = LocalValidationReceiptV1(
            source_commit=payload["source_commit"],
            checkout_clean=payload["checkout_clean"],
            profile=payload["profile"],
            python_version=payload["python_version"],
            go_version=payload["go_version"],
            platform=payload["platform"],
            steps=steps,
            passed=payload["passed"],
            release_eligible=payload["release_eligible"],
            authority=payload["authority"],
            digest=payload["digest"],
            version=payload.get("version", 1),
        )
        receipt.require_for_release(commit)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"validation receipt is not release-valid: {exc}") from exc


def _verify_self_digest(payload: dict[str, object], field: str, label: str) -> None:
    supplied = payload.get(field)
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise ValueError(f"{label} digest is missing")
    unsigned = dict(payload)
    unsigned.pop(field, None)
    canonical = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != supplied:
        raise ValueError(f"{label} digest mismatch")


def _sbom(path: Path, version: str) -> None:
    payload = _json_object(path, "SBOM")
    if payload.get("schema") != SBOM_SCHEMA:
        raise ValueError("SBOM schema mismatch")
    project = payload.get("project")
    if not isinstance(project, dict) or project.get("version") != version:
        raise ValueError("SBOM belongs to a different package version")
    if payload.get("reproducible_inputs") is not True:
        raise ValueError("SBOM does not prove reproducible production inputs")
    if payload.get("mutable_roots") != []:
        raise ValueError("SBOM still reports mutable production roots")
    _verify_self_digest(payload, "sbom_sha256", "SBOM")


def _reproducibility_receipt(path: Path, commit: str, artifact: Path) -> None:
    payload = _json_object(path, "reproducibility receipt")
    if payload.get("schema") != REPRO_SCHEMA:
        raise ValueError("reproducibility receipt schema mismatch")
    if payload.get("source_commit") != commit:
        raise ValueError("reproducibility receipt belongs to a different source commit")
    if payload.get("independent_builds") != 2 or payload.get("byte_identical") is not True:
        raise ValueError("reproducibility receipt does not prove two byte-identical builds")
    if payload.get("authority") is not False:
        raise ValueError("reproducibility receipt cannot carry authority")
    if payload.get("artifact_sha256") != sha256_file(artifact):
        raise ValueError("reproducibility receipt artifact digest mismatch")
    if payload.get("artifact_bytes") != artifact.stat().st_size:
        raise ValueError("reproducibility receipt artifact size mismatch")
    _verify_self_digest(payload, "receipt_sha256", "reproducibility receipt")


def build_manifest(
    *,
    root: Path,
    tag: str,
    source_archive: Path,
    build_artifact: Path,
    validation_receipt: Path,
    reproducibility_receipt: Path,
    sbom: Path,
    benchmark_dossier: Path,
    threat_model: Path,
    license_lineage: Path,
    signing_identity: str,
) -> dict[str, object]:
    require_clean_tree(root)
    commit = git_head(root)
    version = project_version(root)
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(
            f"candidate tag/version mismatch: expected {expected_tag!r}, got {tag!r}"
        )
    if not signing_identity.strip():
        raise ValueError(
            "signing identity must be explicit; use a scoped 'not-deployed' statement if necessary"
        )

    _validation_receipt(validation_receipt, commit)
    _sbom(sbom, version)
    _reproducibility_receipt(reproducibility_receipt, commit, build_artifact)

    evidence = {
        "source_archive": evidence_record(source_archive),
        "build_artifact": evidence_record(build_artifact),
        "validation_receipt": evidence_record(validation_receipt),
        "reproducibility_receipt": evidence_record(reproducibility_receipt),
        "sbom": evidence_record(sbom),
        "benchmark_dossier": evidence_record(benchmark_dossier),
        "threat_model": evidence_record(threat_model),
        "license_lineage": evidence_record(license_lineage),
    }
    release_inputs = {
        relative: evidence_record(root / relative) for relative in RELEASE_INPUTS
    }
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "repository": REPOSITORY,
        "commit": commit,
        "version": version,
        "tag": tag,
        "signing_identity": signing_identity.strip(),
        "release_inputs": release_inputs,
        "evidence": evidence,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--build-artifact", type=Path, required=True)
    parser.add_argument("--validation-receipt", type=Path, required=True)
    parser.add_argument("--reproducibility-receipt", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--benchmark-dossier", type=Path, required=True)
    parser.add_argument("--threat-model", type=Path, required=True)
    parser.add_argument("--license-lineage", type=Path, required=True)
    parser.add_argument("--signing-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = args.root.resolve()
    manifest = build_manifest(
        root=root,
        tag=args.tag,
        source_archive=args.source_archive,
        build_artifact=args.build_artifact,
        validation_receipt=args.validation_receipt,
        reproducibility_receipt=args.reproducibility_receipt,
        sbom=args.sbom,
        benchmark_dossier=args.benchmark_dossier,
        threat_model=args.threat_model,
        license_lineage=args.license_lineage,
        signing_identity=args.signing_identity,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
