from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.validate_production_container_lock_v1 import (
    ProductionContainerLockError,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_production_container_lock_is_exact_and_fail_closed():
    validate(REPO_ROOT)


def test_snapshot_override_guard_is_required(tmp_path: Path):
    lock = json.loads((REPO_ROOT / "production-container-lock.json").read_text(encoding="utf-8"))
    (tmp_path / "production-container-lock.json").write_text(
        json.dumps(lock), encoding="utf-8"
    )
    docker = (REPO_ROOT / "Dockerfile.production").read_text(encoding="utf-8")
    docker = docker.replace(
        '    test "${DEBIAN_SNAPSHOT}" = "20260901T000000Z"; \\\n',
        "",
        1,
    )
    (tmp_path / "Dockerfile.production").write_text(docker, encoding="utf-8")

    with pytest.raises(ProductionContainerLockError, match="not fail-closed"):
        validate(tmp_path)


def test_image_digest_drift_is_rejected(tmp_path: Path):
    lock = json.loads((REPO_ROOT / "production-container-lock.json").read_text(encoding="utf-8"))
    (tmp_path / "production-container-lock.json").write_text(
        json.dumps(lock), encoding="utf-8"
    )
    docker = (REPO_ROOT / "Dockerfile.production").read_text(encoding="utf-8")
    docker = docker.replace(
        lock["images"]["python_runtime"],
        "python:3.12-slim-bookworm",
        1,
    )
    (tmp_path / "Dockerfile.production").write_text(docker, encoding="utf-8")

    with pytest.raises(ProductionContainerLockError, match="image roots drifted"):
        validate(tmp_path)
