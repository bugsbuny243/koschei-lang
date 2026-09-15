#!/usr/bin/env python3
"""Generate a deterministic acquisition/release SBOM root snapshot.

This is an evidence generator, not a vulnerability scanner. Production
reproducibility is evaluated from ``Dockerfile.production`` plus explicit lock
files. The mutable Railway/testnet Dockerfile is intentionally not release
authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

SCHEMA = "koschei.acquisition-sbom/v1"
CONTAINER_LOCK_SCHEMA = "koschei.production-container-lock/v1"
PRODUCTION_DOCKERFILE = "Dockerfile.production"
CONTAINER_LOCK = "production-container-lock.json"
PYTHON_LOCKS = (
    "production-build-bootstrap.txt",
    "production-build-requirements.txt",
)
_IMAGE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_SNAPSHOT = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
_EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(root: Path, relative: str) -> bytes:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"required SBOM input is missing: {relative}")
    return path.read_bytes()


def _docker_from_images(text: str) -> tuple[str, ...]:
    images: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            images.append(stripped.split()[1])
    return tuple(images)


def _normalize_docker_run(text: str) -> str:
    return text.replace("\\\n", " ")


def _docker_pip_packages(text: str) -> tuple[str, ...]:
    """Return only inline package specs, excluding requirement files."""

    normalized = _normalize_docker_run(text)
    packages: list[str] = []
    for match in re.finditer(r"python -m pip install\s+(.+?)(?=\s+&&|$)", normalized):
        tokens = match.group(1).strip().split()
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token in {"-r", "--requirement"}:
                skip_next = True
                continue
            if token.startswith("--requirement="):
                continue
            if token.startswith("-"):
                continue
            packages.append(token)
    return tuple(packages)


def _docker_requirement_files(text: str) -> tuple[str, ...]:
    normalized = _normalize_docker_run(text)
    files: list[str] = []
    for match in re.finditer(r"python -m pip install\s+(.+?)(?=\s+&&|$)", normalized):
        tokens = match.group(1).strip().split()
        for index, token in enumerate(tokens):
            if token in {"-r", "--requirement"} and index + 1 < len(tokens):
                files.append(Path(tokens[index + 1]).name)
            elif token.startswith("--requirement="):
                files.append(Path(token.split("=", 1)[1]).name)
    return tuple(files)


def _apt_packages(text: str) -> tuple[str, ...]:
    normalized = _normalize_docker_run(text)
    packages: list[str] = []
    for match in re.finditer(
        r"apt-get(?:\s+-o\s+[^\s]+)*\s+install\s+-y\s+--no-install-recommends\s+(.+?)(?=\s*;|\s+&&|$)",
        normalized,
    ):
        packages.extend(match.group(1).strip().split())
    return tuple(packages)


def _normalized_python_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _requirement_name(requirement: str) -> str:
    return _normalized_python_name(re.split(r"[<>=!~\s]", requirement, 1)[0])


def _parse_hash_lock(text: str, source: str) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:([0-9a-fA-F]{64})",
            line,
        )
        if match is None:
            raise ValueError(
                f"invalid hash-bound Python lock entry in {source}:{line_number}"
            )
        name, version, digest = match.groups()
        rows.append(
            {
                "name": _normalized_python_name(name),
                "version": version,
                "sha256": digest.lower(),
                "source": source,
            }
        )
    if not rows:
        raise ValueError(f"Python build lock is empty: {source}")
    return tuple(rows)


def _container_lock(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.get("schema") != CONTAINER_LOCK_SCHEMA:
        raise ValueError("production container lock has invalid schema")
    if payload.get("platform") != "linux/amd64":
        raise ValueError("production container lock must target linux/amd64")
    images = payload.get("images")
    snapshot = payload.get("debian_snapshot")
    if not isinstance(images, dict) or not isinstance(snapshot, dict):
        raise ValueError("production container lock is structurally incomplete")
    required_images = ("go_toolchain", "python_builder", "python_runtime")
    for name in required_images:
        value = images.get(name)
        if not isinstance(value, str) or _IMAGE_DIGEST.search(value) is None:
            raise ValueError(f"production container image is not digest pinned: {name}")
    timestamp = snapshot.get("timestamp")
    if not isinstance(timestamp, str) or _SNAPSHOT.fullmatch(timestamp) is None:
        raise ValueError("Debian snapshot timestamp must be YYYYMMDDThhmmssZ")
    if snapshot.get("suite") != "bookworm" or snapshot.get("security_suite") != "bookworm-security":
        raise ValueError("production Debian snapshot suite drifted")
    return payload


def build_sbom(root: Path) -> dict[str, object]:
    pyproject_bytes = _read(root, "pyproject.toml")
    go_mod_bytes = _read(root, "native/go.mod")
    docker_bytes = _read(root, PRODUCTION_DOCKERFILE)
    container_lock_bytes = _read(root, CONTAINER_LOCK)
    lock_bytes = {relative: _read(root, relative) for relative in PYTHON_LOCKS}

    pyproject = tomllib.loads(pyproject_bytes.decode("utf-8"))
    project = pyproject.get("project", {})
    build_system = pyproject.get("build-system", {})
    runtime_dependencies = tuple(project.get("dependencies", ()))
    build_requirements = tuple(build_system.get("requires", ()))

    locked_rows = tuple(
        row
        for relative in PYTHON_LOCKS
        for row in _parse_hash_lock(lock_bytes[relative].decode("utf-8"), relative)
    )
    locked_by_name: dict[str, dict[str, str]] = {}
    for row in locked_rows:
        name = row["name"]
        if name in locked_by_name:
            raise ValueError(f"duplicate Python build lock entry for {name}")
        locked_by_name[name] = row

    container_lock = _container_lock(json.loads(container_lock_bytes.decode("utf-8")))
    locked_images = container_lock["images"]
    assert isinstance(locked_images, dict)
    locked_snapshot = container_lock["debian_snapshot"]
    assert isinstance(locked_snapshot, dict)

    go_text = go_mod_bytes.decode("utf-8")
    external_go_requirements = tuple(
        line.strip() for line in go_text.splitlines() if line.strip().startswith("require ")
    )

    docker_text = docker_bytes.decode("utf-8")
    base_images = _docker_from_images(docker_text)
    apt_packages = _apt_packages(docker_text)
    docker_pip_packages = _docker_pip_packages(docker_text)
    docker_requirement_files = _docker_requirement_files(docker_text)

    expected_images = (
        locked_images["go_toolchain"],
        locked_images["python_builder"],
        locked_images["python_runtime"],
    )
    mutable_roots: list[str] = []
    if base_images != expected_images:
        mutable_roots.append("production-container-lock:dockerfile-image-drift")
    for image in base_images:
        if _IMAGE_DIGEST.search(image) is None:
            mutable_roots.append(f"container-image:{image}")

    snapshot = str(locked_snapshot["timestamp"])
    required_snapshot_fragments = (
        "snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/",
        "snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/",
        f"ARG DEBIAN_SNAPSHOT={snapshot}",
        "[check-valid-until=no]",
    )
    if any(fragment not in docker_text for fragment in required_snapshot_fragments):
        mutable_roots.append("debian-snapshot:dockerfile-lock-drift")

    for req in build_requirements:
        name = _requirement_name(req)
        locked = locked_by_name.get(name)
        if locked is None:
            mutable_roots.append(f"python-build:{req}")
            continue
        exact = _EXACT_REQUIREMENT.fullmatch(req)
        if exact is None or exact.group(2) != locked["version"]:
            mutable_roots.append(f"python-build-version-drift:{req}")
    for package in docker_pip_packages:
        name = _requirement_name(package)
        if name not in locked_by_name:
            mutable_roots.append(f"docker-pip:{package}")
    for lock_name in PYTHON_LOCKS:
        if lock_name not in docker_requirement_files:
            mutable_roots.append(f"docker-python-lock-not-consumed:{lock_name}")

    payload: dict[str, object] = {
        "schema": SCHEMA,
        "project": {
            "name": project.get("name"),
            "version": project.get("version"),
            "runtime_dependencies": list(runtime_dependencies),
        },
        "python_build": {
            "backend": build_system.get("build-backend"),
            "requirements": list(build_requirements),
            "artifact_locks": list(locked_rows),
        },
        "native_go": {
            "module_file_sha256": _sha256_bytes(go_mod_bytes),
            "external_requirements": list(external_go_requirements),
        },
        "container": {
            "dockerfile": PRODUCTION_DOCKERFILE,
            "dockerfile_sha256": _sha256_bytes(docker_bytes),
            "platform": container_lock["platform"],
            "base_images": list(base_images),
            "debian_snapshot": dict(locked_snapshot),
            "apt_packages": list(apt_packages),
            "inline_pip_packages": list(docker_pip_packages),
            "python_requirement_files": list(docker_requirement_files),
        },
        "source_inputs": {
            "pyproject_toml_sha256": _sha256_bytes(pyproject_bytes),
            "native_go_mod_sha256": _sha256_bytes(go_mod_bytes),
            "production_dockerfile_sha256": _sha256_bytes(docker_bytes),
            "production_container_lock_sha256": _sha256_bytes(container_lock_bytes),
            "python_lock_sha256": {
                relative: _sha256_bytes(data) for relative, data in sorted(lock_bytes.items())
            },
        },
        "mutable_roots": sorted(set(mutable_roots)),
    }
    payload["reproducible_inputs"] = not bool(payload["mutable_roots"])
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload["sbom_sha256"] = _sha256_bytes(canonical)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require-reproducible",
        action="store_true",
        help="fail if any mutable/unpinned production build root remains",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = build_sbom(args.root.resolve())
    if args.require_reproducible and not payload["reproducible_inputs"]:
        raise SystemExit(
            "acquisition SBOM refused: mutable/unpinned roots remain: "
            + ", ".join(payload["mutable_roots"])
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
