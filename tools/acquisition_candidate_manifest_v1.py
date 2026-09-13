#!/usr/bin/env python3
"""Create a fail-closed acquisition-candidate evidence manifest.

This tool does not decide that a candidate is buyer-ready. It binds already
produced evidence files to one immutable Git commit and package version so a
reviewer can verify that release, validation, SBOM, benchmark and threat-model
artifacts all refer to the same candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

REPOSITORY = "bugsbuny243/koschei-lang"
SCHEMA = "koschei.acquisition-candidate/v1"


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


def build_manifest(
    *,
    root: Path,
    tag: str,
    source_archive: Path,
    build_artifact: Path,
    validation_receipt: Path,
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

    evidence = {
        "source_archive": evidence_record(source_archive),
        "build_artifact": evidence_record(build_artifact),
        "validation_receipt": evidence_record(validation_receipt),
        "sbom": evidence_record(sbom),
        "benchmark_dossier": evidence_record(benchmark_dossier),
        "threat_model": evidence_record(threat_model),
        "license_lineage": evidence_record(license_lineage),
    }
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "repository": REPOSITORY,
        "commit": commit,
        "version": version,
        "tag": tag,
        "signing_identity": signing_identity.strip(),
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
