from __future__ import annotations

from pathlib import Path

from tools import acquisition_sbom_v1 as sbom


def _fixture_repo(tmp_path: Path, *, pinned: bool) -> Path:
    (tmp_path / "native").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        """[build-system]\nrequires = [\"setuptools==80.0.0 --hash=sha256:abc\"]\nbuild-backend = \"setuptools.build_meta\"\n\n[project]\nname = \"koschei-lang\"\nversion = \"0.10.0\"\ndependencies = []\n""",
        encoding="utf-8",
    )
    (tmp_path / "native" / "go.mod").write_text(
        "module example.invalid/koschei/native\n\ngo 1.22\n",
        encoding="utf-8",
    )
    if pinned:
        docker = """FROM python:3.12-bookworm@sha256:deadbeef AS builder\nRUN apt-get update && apt-get install -y --no-install-recommends openssl=3.0.0 && rm -rf /var/lib/apt/lists/*\nRUN python -m pip install nuitka==2.0.0 --hash=sha256:cafe\nFROM python:3.12-slim-bookworm@sha256:feedface AS runtime\n"""
    else:
        docker = """FROM python:3.12-bookworm AS builder\nRUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*\nRUN python -m pip install --no-cache-dir --upgrade pip \\\n    && python -m pip install --no-cache-dir nuitka ordered-set zstandard\nFROM python:3.12-slim-bookworm AS runtime\n"""
    (tmp_path / "Dockerfile").write_text(docker, encoding="utf-8")
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
    assert first["reproducible_inputs"] is True
    assert first["mutable_roots"] == []
    assert len(first["sbom_sha256"]) == 64


def test_unpinned_docker_roots_are_reported_fail_closed(tmp_path: Path):
    root = _fixture_repo(tmp_path, pinned=False)

    result = sbom.build_sbom(root)

    assert result["reproducible_inputs"] is False
    roots = set(result["mutable_roots"])
    assert "container-image:python:3.12-bookworm" in roots
    assert "container-image:python:3.12-slim-bookworm" in roots
    assert "apt:openssl" in roots
    assert "docker-pip:pip" in roots
    assert "docker-pip:nuitka" in roots
    assert "docker-pip:ordered-set" in roots
    assert "docker-pip:zstandard" in roots


def test_missing_required_input_is_rejected(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nversion='0.10.0'\n", encoding="utf-8")

    try:
        sbom.build_sbom(tmp_path)
    except ValueError as exc:
        assert "required SBOM input is missing" in str(exc)
    else:
        raise AssertionError("missing go.mod/Dockerfile must fail closed")
