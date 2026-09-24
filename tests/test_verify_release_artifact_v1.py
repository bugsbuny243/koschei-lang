from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from tools.verify_release_artifact_v1 import ReleaseArtifactVerificationError, verify_archive


def _archive(path: Path, *, commit: str = "a" * 40, version: str = "0.10.0", binary: bytes = b"koschei-bin", lock_override: dict | None = None) -> None:
    manifest = {
        "schema": "koschei.solohost-release-manifest/v1",
        "product": "koschei-lang",
        "channel": "pi-solohost",
        "version": version,
        "platform": "linux-x86_64",
        "source_commit": commit,
        "entrypoint": "ks",
        "artifact": {"path": "ks", "sha256": hashlib.sha256(binary).hexdigest(), "size_bytes": len(binary)},
        "signature": {"status": "UNSIGNED-STAGING", "scheme": None, "key_id": None, "signature_file": None},
    }
    lock = lock_override or {
        "schema": "koschei.production-container-lock/v1",
        "platform": "linux/amd64",
        "images": {
            "go_toolchain": "golang@sha256:" + "1" * 64,
            "python_builder": "python@sha256:" + "2" * 64,
            "python_runtime": "python@sha256:" + "3" * 64,
        },
    }
    members = {
        "ks": binary,
        "koschei-release-manifest.json": json.dumps(manifest).encode(),
        "production-container-lock.json": json.dumps(lock).encode(),
        "production-build-bootstrap.txt": b"setuptools==84.0.0 --hash=sha256:" + b"4" * 64,
        "production-build-requirements.txt": b"Nuitka==4.2.1 --hash=sha256:" + b"5" * 64,
        "koschei-debian-build-packages.tsv": b"patchelf\t0.14.3-1+b1\n",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_release_archive_verifier_binds_commit_binary_and_release_inputs(tmp_path: Path):
    artifact = tmp_path / "release.zip"
    _archive(artifact)
    receipt = verify_archive(artifact, expected_commit="a" * 40, expected_version="0.10.0")
    assert receipt["passed"] is True
    assert receipt["authority"] is False
    assert receipt["source_commit"] == "a" * 40
    assert receipt["executable_sha256"] == hashlib.sha256(b"koschei-bin").hexdigest()
    assert set(receipt["release_inputs"]) == {
        "koschei-debian-build-packages.tsv",
        "production-build-bootstrap.txt",
        "production-build-requirements.txt",
        "production-container-lock.json",
    }
    assert len(receipt["verification_sha256"]) == 64


def test_wrong_candidate_commit_fails_closed(tmp_path: Path):
    artifact = tmp_path / "release.zip"
    _archive(artifact)
    with pytest.raises(ReleaseArtifactVerificationError, match="source commit mismatch"):
        verify_archive(artifact, expected_commit="b" * 40, expected_version="0.10.0")


def test_tampered_binary_fails_closed(tmp_path: Path):
    artifact = tmp_path / "release.zip"
    _archive(artifact)
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr("ks", b"tampered")
    with pytest.raises(ReleaseArtifactVerificationError, match="duplicate member"):
        verify_archive(artifact, expected_commit="a" * 40, expected_version="0.10.0")


def test_mutable_container_root_fails_closed(tmp_path: Path):
    artifact = tmp_path / "release.zip"
    _archive(
        artifact,
        lock_override={
            "schema": "koschei.production-container-lock/v1",
            "platform": "linux/amd64",
            "images": {"python_runtime": "python:3.12-slim-bookworm"},
        },
    )
    with pytest.raises(ReleaseArtifactVerificationError, match="not digest-pinned"):
        verify_archive(artifact, expected_commit="a" * 40, expected_version="0.10.0")


def test_empty_debian_inventory_fails_closed(tmp_path: Path):
    artifact = tmp_path / "release.zip"
    _archive(artifact)
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(artifact, "r") as archive:
        for info in archive.infolist():
            entries[info.filename] = archive.read(info.filename)
    entries["koschei-debian-build-packages.tsv"] = b""
    artifact.unlink()
    with zipfile.ZipFile(artifact, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    with pytest.raises(ReleaseArtifactVerificationError, match="inventory is empty"):
        verify_archive(artifact, expected_commit="a" * 40, expected_version="0.10.0")
