from __future__ import annotations

import json
from pathlib import Path

from tools import acquisition_sbom_v1 as sbom


_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_DIGEST_C = "c" * 64
_HASH_D = "d" * 64
_HASH_E = "e" * 64


def _fixture_repo(tmp_path: Path, *, pinned: bool) -> Path:
    (tmp_path / "native").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        """[build-system]\nrequires = [\"setuptools==84.0.0\"]\nbuild-backend = \"setuptools.build_meta\"\n\n[project]\nname = \"koschei-lang\"\nversion = \"0.10.0\"\ndependencies = []\n""",
        encoding="utf-8",
    )
    (tmp_path / "native" / "go.mod").write_text(
        "module example.invalid/koschei/native\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (tmp_path / "production-build-bootstrap.txt").write_text(
        f"setuptools==84.0.0 --hash=sha256:{_HASH_D}\n",
        encoding="utf-8",
    )
    (tmp_path / "production-build-requirements.txt").write_text(
        f"nuitka==4.2.1 --hash=sha256:{_HASH_E}\n",
        encoding="utf-8",
    )

    go_image = f"golang:1.24-bookworm@sha256:{_DIGEST_A}"
    builder_image = f"python:3.12-bookworm@sha256:{_DIGEST_B}"
    runtime_image = f"python:3.12-slim-bookworm@sha256:{_DIGEST_C}"
    container_lock = {
        "schema": "koschei.production-container-lock/v1",
        "platform": "linux/amd64",
        "images": {
            "go_toolchain": go_image,
            "python_builder": builder_image,
            "python_runtime": runtime_image,
        },
        "debian_snapshot": {
            "timestamp": "20260901T000000Z",
            "suite": "bookworm",
            "security_suite": "bookworm-security",
        },
    }
    (tmp_path / "production-container-lock.json").write_text(
        json.dumps(container_lock), encoding="utf-8"
    )

    if pinned:
        docker = f"""FROM {go_image} AS go-toolchain
FROM {builder_image} AS builder
ARG DEBIAN_SNAPSHOT=20260901T000000Z
RUN printf '%s\\n' \\
  \"deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${{DEBIAN_SNAPSHOT}}/ bookworm main\" \\
  \"deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/${{DEBIAN_SNAPSHOT}}/ bookworm-security main\" > /etc/apt/sources.list; \\
  apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends openssl
COPY production-build-bootstrap.txt /tmp/production-build-bootstrap.txt
COPY production-build-requirements.txt /tmp/production-build-requirements.txt
RUN python -m pip install --require-hashes -r /tmp/production-build-bootstrap.txt \\
 && python -m pip install --require-hashes -r /tmp/production-build-requirements.txt
FROM {runtime_image} AS runtime
"""
    else:
        docker = """FROM golang:1.24-bookworm AS go-toolchain
FROM python:3.12-bookworm AS builder
ARG DEBIAN_SNAPSHOT=latest
RUN apt-get install -y --no-install-recommends openssl
RUN python -m pip install nuitka
FROM python:3.12-slim-bookworm AS runtime
"""
    (tmp_path / "Dockerfile.production").write_text(docker, encoding="utf-8")
    return tmp_path


def test_sbom_binds_declared_inputs_and_is_deterministic(tmp_path: Path):
    root = _fixture_repo(tmp_path, pinned=True)

    first = sbom.build_sbom(root)
    second = sbom.build_sbom(root)

    assert first == second
    assert first["schema"] == "koschei.acquisition-sbom/v1"
    assert first["project"]["version"] == "0.10.0"
    assert first["project"]["runtime_dependencies"] == []
    assert first["native_go"]["external_requirements"] == []
    assert first["container"]["dockerfile"] == "Dockerfile.production"
    assert first["container"]["platform"] == "linux/amd64"
    assert first["reproducible_inputs"] is True
    assert first["mutable_roots"] == []
    assert len(first["sbom_sha256"]) == 64


def test_declared_build_version_must_match_hash_lock(tmp_path: Path):
    root = _fixture_repo(tmp_path, pinned=True)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "setuptools==84.0.0", "setuptools==83.0.0"
        ),
        encoding="utf-8",
    )

    result = sbom.build_sbom(root)

    assert result["reproducible_inputs"] is False
    assert "python-build-version-drift:setuptools==83.0.0" in set(result["mutable_roots"])


def test_dockerfile_drift_from_container_lock_is_reported(tmp_path: Path):
    root = _fixture_repo(tmp_path, pinned=False)

    result = sbom.build_sbom(root)

    assert result["reproducible_inputs"] is False
    roots = set(result["mutable_roots"])
    assert "production-container-lock:dockerfile-image-drift" in roots
    assert "container-image:golang:1.24-bookworm" in roots
    assert "container-image:python:3.12-bookworm" in roots
    assert "container-image:python:3.12-slim-bookworm" in roots
    assert "debian-snapshot:dockerfile-lock-drift" in roots
    assert "docker-pip:nuitka" in roots
    assert "docker-python-lock-not-consumed:production-build-bootstrap.txt" in roots


def test_invalid_container_lock_digest_is_rejected(tmp_path: Path):
    root = _fixture_repo(tmp_path, pinned=True)
    lock_path = root / "production-container-lock.json"
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["images"]["python_builder"] = "python:3.12-bookworm"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        sbom.build_sbom(root)
    except ValueError as exc:
        assert "not digest pinned" in str(exc)
    else:
        raise AssertionError("mutable production image lock must fail closed")


def test_missing_required_input_is_rejected(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nversion='0.10.0'\n", encoding="utf-8"
    )

    try:
        sbom.build_sbom(tmp_path)
    except ValueError as exc:
        assert "required SBOM input is missing" in str(exc)
    else:
        raise AssertionError("missing production release inputs must fail closed")
