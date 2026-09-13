#!/usr/bin/env python3
"""Generate a deterministic acquisition SBOM snapshot from repository declarations.

This is an evidence generator, not a vulnerability scanner. It records declared
runtime/build/toolchain roots and explicitly marks mutable/unpinned inputs so an
acquisition candidate cannot present an incomplete dependency picture as
reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

SCHEMA = "koschei.acquisition-sbom/v1"


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
        if not stripped.upper().startswith("FROM "):
            continue
        images.append(stripped.split()[1])
    return tuple(images)


def _normalize_docker_run(text: str) -> str:
    return text.replace("\\\n", " ")


def _docker_pip_packages(text: str) -> tuple[str, ...]:
    normalized = _normalize_docker_run(text)
    packages: list[str] = []
    for match in re.finditer(r"python -m pip install\s+(.+?)(?=\s+&&|$)", normalized):
        tokens = match.group(1).strip().split()
        for token in tokens:
            if token.startswith("-"):
                continue
            packages.append(token)
    return tuple(packages)


def _apt_packages(text: str) -> tuple[str, ...]:
    normalized = _normalize_docker_run(text)
    packages: list[str] = []
    for match in re.finditer(
        r"apt-get install\s+-y\s+--no-install-recommends\s+(.+?)(?=\s+&&|$)",
        normalized,
    ):
        packages.extend(match.group(1).strip().split())
    return tuple(packages)


def _is_immutable_image(image: str) -> bool:
    return "@sha256:" in image


def _is_exact_python_requirement(requirement: str) -> bool:
    # Acquisition mode is deliberately stricter than normal packaging. A bare
    # name, range or exact version without an artifact hash remains mutable.
    return "==" in requirement and "--hash=" in requirement


def build_sbom(root: Path) -> dict[str, object]:
    pyproject_bytes = _read(root, "pyproject.toml")
    go_mod_bytes = _read(root, "native/go.mod")
    docker_bytes = _read(root, "Dockerfile")

    pyproject = tomllib.loads(pyproject_bytes.decode("utf-8"))
    project = pyproject.get("project", {})
    build_system = pyproject.get("build-system", {})
    runtime_dependencies = tuple(project.get("dependencies", ()))
    build_requirements = tuple(build_system.get("requires", ()))

    go_text = go_mod_bytes.decode("utf-8")
    external_go_requirements = tuple(
        line.strip() for line in go_text.splitlines() if line.strip().startswith("require ")
    )

    docker_text = docker_bytes.decode("utf-8")
    base_images = _docker_from_images(docker_text)
    apt_packages = _apt_packages(docker_text)
    docker_pip_packages = _docker_pip_packages(docker_text)

    mutable_roots: list[str] = []
    for image in base_images:
        if not _is_immutable_image(image):
            mutable_roots.append(f"container-image:{image}")
    for req in build_requirements:
        if not _is_exact_python_requirement(req):
            mutable_roots.append(f"python-build:{req}")
    for package in apt_packages:
        if "=" not in package:
            mutable_roots.append(f"apt:{package}")
    for package in docker_pip_packages:
        if not _is_exact_python_requirement(package):
            mutable_roots.append(f"docker-pip:{package}")

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
        },
        "native_go": {
            "module_file_sha256": _sha256_bytes(go_mod_bytes),
            "external_requirements": list(external_go_requirements),
        },
        "container": {
            "dockerfile_sha256": _sha256_bytes(docker_bytes),
            "base_images": list(base_images),
            "apt_packages": list(apt_packages),
            "pip_packages": list(docker_pip_packages),
        },
        "source_inputs": {
            "pyproject_toml_sha256": _sha256_bytes(pyproject_bytes),
            "native_go_mod_sha256": _sha256_bytes(go_mod_bytes),
            "dockerfile_sha256": _sha256_bytes(docker_bytes),
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
        help="fail if any mutable/unpinned build root remains",
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
