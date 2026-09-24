#!/usr/bin/env python3
"""Validate Dockerfile.production against the immutable production container lock."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = "koschei.production-container-lock/v1"
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_SNAPSHOT = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")


class ProductionContainerLockError(ValueError):
    pass


def validate(root: Path) -> None:
    docker_path = root / "Dockerfile.production"
    lock_path = root / "production-container-lock.json"
    if not docker_path.is_file() or not lock_path.is_file():
        raise ProductionContainerLockError("production Dockerfile/lock input is missing")
    docker = docker_path.read_text(encoding="utf-8")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ProductionContainerLockError("production container lock schema mismatch")
    if payload.get("platform") != "linux/amd64":
        raise ProductionContainerLockError("production platform must be linux/amd64")

    images = payload.get("images")
    snapshot = payload.get("debian_snapshot")
    if not isinstance(images, dict) or not isinstance(snapshot, dict):
        raise ProductionContainerLockError("production container lock is incomplete")
    ordered = (
        images.get("go_toolchain"),
        images.get("python_builder"),
        images.get("python_runtime"),
    )
    if any(not isinstance(value, str) or _DIGEST.search(value) is None for value in ordered):
        raise ProductionContainerLockError("all production images must be digest pinned")
    from_images = tuple(
        line.strip().split()[1]
        for line in docker.splitlines()
        if line.strip().upper().startswith("FROM ")
    )
    if from_images != ordered:
        raise ProductionContainerLockError("Dockerfile production image roots drifted from lock")

    timestamp = snapshot.get("timestamp")
    if not isinstance(timestamp, str) or _SNAPSHOT.fullmatch(timestamp) is None:
        raise ProductionContainerLockError("Debian snapshot timestamp is invalid")
    if snapshot.get("suite") != "bookworm" or snapshot.get("security_suite") != "bookworm-security":
        raise ProductionContainerLockError("Debian snapshot suites drifted")

    required = (
        f"ARG DEBIAN_SNAPSHOT={timestamp}",
        f'test "${{DEBIAN_SNAPSHOT}}" = "{timestamp}";',
        "snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/",
        "snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/",
        "[check-valid-until=no]",
    )
    missing = [fragment for fragment in required if fragment not in docker]
    if missing:
        raise ProductionContainerLockError(
            "production snapshot lock is not fail-closed: " + ", ".join(missing)
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        validate(args.root.resolve())
    except (OSError, json.JSONDecodeError, ProductionContainerLockError) as exc:
        raise SystemExit(f"production container lock refused: {exc}") from exc
    print("production container lock: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
