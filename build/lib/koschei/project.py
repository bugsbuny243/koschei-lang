"""Koschei project manifests and zero-dependency project scaffolding."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_NAME = "koschei.toml"
PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
SEMVER = re.compile(r"^(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){2}(?:[-+][0-9A-Za-z.-]+)?$")


class ProjectError(ValueError):
    """A project manifest or scaffold request is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: Path
    manifest: Path
    name: str
    version: str
    entry: Path


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def load_project(path: str | Path) -> ProjectConfig:
    requested = Path(path)
    manifest = requested if requested.name == MANIFEST_NAME else requested / MANIFEST_NAME
    manifest = manifest.resolve()
    if not manifest.is_file():
        raise ProjectError(f"Project manifest not found: {manifest}")

    try:
        data: dict[str, Any] = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ProjectError(f"Invalid {MANIFEST_NAME}: {error}") from error

    package = data.get("package")
    if not isinstance(package, dict):
        raise ProjectError(f"{MANIFEST_NAME} must contain a [package] table")

    name = package.get("name")
    version = package.get("version")
    entry_text = package.get("entry", "src/main.ks")
    if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name):
        raise ProjectError(
            "package.name must start with a lowercase letter and contain only "
            "lowercase letters, digits, '-' or '_'"
        )
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ProjectError("package.version must be a semantic version such as 0.1.0")
    if not isinstance(entry_text, str) or not entry_text.endswith(".ks"):
        raise ProjectError("package.entry must be a relative .ks source path")

    root = manifest.parent.resolve()
    entry = (root / entry_text).resolve()
    if not _inside(root, entry):
        raise ProjectError("package.entry cannot escape the project directory")
    if not entry.is_file():
        raise ProjectError(f"Project entry source not found: {entry}")

    return ProjectConfig(
        root=root,
        manifest=manifest,
        name=name,
        version=version,
        entry=entry,
    )


def resolve_source(path: str | Path) -> Path:
    requested = Path(path)
    if requested.is_dir() or requested.name == MANIFEST_NAME:
        return load_project(requested).entry
    return requested


def create_project(name: str, destination: str | Path | None = None) -> ProjectConfig:
    if not PACKAGE_NAME.fullmatch(name):
        raise ProjectError(
            "Project name must start with a lowercase letter and contain only "
            "lowercase letters, digits, '-' or '_'"
        )

    root = Path(destination) if destination is not None else Path(name)
    root = root.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProjectError(f"Destination is not empty: {root}")

    source_dir = root / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest = root / MANIFEST_NAME
    entry = source_dir / "main.ks"

    manifest.write_text(
        "[package]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'entry = "src/main.ks"\n\n'
        "[capabilities]\n"
        "disk = []\n"
        "net = []\n"
        "env = []\n"
        "process = false\n",
        encoding="utf-8",
    )
    entry.write_text(
        "fn main() {\n"
        f'    println("Hello from {name}")\n'
        "}\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n.koschei/\nbuild/\ndist/\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"# {name}\n\n"
        "```sh\n"
        "ks check .\n"
        "ks run .\n"
        "ks build . -o ./app\n"
        "```\n",
        encoding="utf-8",
    )
    return load_project(root)
