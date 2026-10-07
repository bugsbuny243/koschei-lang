#!/usr/bin/env python3
"""Fail-closed verification of a Koschei SoloHost release ZIP.

This verifier binds the customer archive to its embedded release manifest and to
its immutable release-input evidence. It does not grant publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

MANIFEST_NAME = "koschei-release-manifest.json"
SCHEMA = "koschei.solohost-release-manifest/v1"
LOCK_SCHEMA = "koschei.production-container-lock/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_EVIDENCE = {
    "production-container-lock.json",
    "production-build-bootstrap.txt",
    "production-build-requirements.txt",
    "koschei-debian-build-packages.tsv",
}


class ReleaseArtifactVerificationError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseArtifactVerificationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseArtifactVerificationError(f"{label} must be a JSON object")
    return value


def verify_archive(path: Path, *, expected_commit: str, expected_version: str) -> dict[str, object]:
    commit = expected_commit.strip().lower()
    if _HEX40.fullmatch(commit) is None:
        raise ReleaseArtifactVerificationError("expected commit must be a full lowercase Git SHA-1")
    version = expected_version.strip()
    if not version or any(ch.isspace() for ch in version):
        raise ReleaseArtifactVerificationError("expected version must be one non-empty token")
    if not path.is_file():
        raise ReleaseArtifactVerificationError(f"release archive does not exist: {path}")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ReleaseArtifactVerificationError("release archive contains duplicate member names")
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
                    raise ReleaseArtifactVerificationError(f"unsafe release archive member: {name!r}")
            required = {MANIFEST_NAME, "ks", *REQUIRED_EVIDENCE}
            missing = sorted(required.difference(names))
            if missing:
                raise ReleaseArtifactVerificationError("release archive is missing required members: " + ", ".join(missing))
            manifest = _json(archive.read(MANIFEST_NAME), "release manifest")
            if manifest.get("schema") != SCHEMA:
                raise ReleaseArtifactVerificationError("release manifest schema mismatch")
            if manifest.get("product") != "koschei-lang" or manifest.get("channel") != "pi-solohost":
                raise ReleaseArtifactVerificationError("release manifest product/channel mismatch")
            if manifest.get("version") != version:
                raise ReleaseArtifactVerificationError("release manifest version mismatch")
            if manifest.get("source_commit") != commit:
                raise ReleaseArtifactVerificationError("release manifest source commit mismatch")
            if manifest.get("entrypoint") != "ks":
                raise ReleaseArtifactVerificationError("linux release entrypoint must be ks")

            artifact = manifest.get("artifact")
            if not isinstance(artifact, dict) or artifact.get("path") != "ks":
                raise ReleaseArtifactVerificationError("release manifest artifact identity mismatch")
            binary = archive.read("ks")
            if artifact.get("sha256") != _sha256(binary) or artifact.get("size_bytes") != len(binary):
                raise ReleaseArtifactVerificationError("release manifest does not bind exact executable bytes")

            signature = manifest.get("signature")
            if not isinstance(signature, dict) or signature.get("status") != "UNSIGNED-STAGING":
                raise ReleaseArtifactVerificationError("candidate verifier only accepts explicit UNSIGNED-STAGING state")

            lock = _json(archive.read("production-container-lock.json"), "production container lock")
            if lock.get("schema") != LOCK_SCHEMA:
                raise ReleaseArtifactVerificationError("production container lock schema mismatch")
            if lock.get("platform") != "linux/amd64":
                raise ReleaseArtifactVerificationError("production container lock platform mismatch")
            images = lock.get("images")
            if not isinstance(images, dict) or not images:
                raise ReleaseArtifactVerificationError("production container lock images are missing")
            for label, image in images.items():
                if not isinstance(image, str) or "@sha256:" not in image:
                    raise ReleaseArtifactVerificationError(f"container image {label!r} is not digest-pinned")
                digest = image.rsplit("@sha256:", 1)[1]
                if _HEX64.fullmatch(digest) is None:
                    raise ReleaseArtifactVerificationError(f"container image {label!r} has invalid digest")

            debian = archive.read("koschei-debian-build-packages.tsv")
            if not debian.strip():
                raise ReleaseArtifactVerificationError("resolved Debian package inventory is empty")

            evidence = {
                name: {"sha256": _sha256(archive.read(name)), "bytes": len(archive.read(name))}
                for name in sorted(REQUIRED_EVIDENCE)
            }
    except zipfile.BadZipFile as exc:
        raise ReleaseArtifactVerificationError("release artifact is not a valid ZIP") from exc

    payload: dict[str, object] = {
        "schema": "koschei.release-artifact-verification/v1",
        "source_commit": commit,
        "version": version,
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "archive_bytes": path.stat().st_size,
        "executable_sha256": artifact["sha256"],
        "release_inputs": evidence,
        "passed": True,
        "authority": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["verification_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = verify_archive(args.artifact, expected_commit=args.expected_commit, expected_version=args.expected_version)
    except (OSError, ReleaseArtifactVerificationError) as exc:
        raise SystemExit(f"release artifact verification refused: {exc}") from exc
    if args.output.exists():
        raise SystemExit(f"release artifact verification refused: output exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
