"""Koschei Packages v1, phase 2: a read-only, static package registry.

A registry is a directory of plain files, served as-is over HTTPS:

    index/<name>.json                       versions, digests and surfaces
    archives/<name>/<name>-<version>.tar    the package's sources

The registry never runs package code. ``ks pkg publish`` checks a package
locally (it loads, type-checks, takes no ``SystemCaps``, and its stated
surface matches the computed one) and writes the two files into a registry
checkout; publishing to koschei.dev is a pull request that a maintainer
merges. Versions are immutable: a published version is never replaced or
deleted, only yanked.

A client never trusts the index's surface: it recomputes the surface from
the downloaded sources and refuses the package if the two differ.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .packages_v1 import (
    DEFAULT_REGISTRY,
    DIGEST,
    VERSION,
    MANIFEST_NAME,
    PACKAGE_NAME,
    SURFACE_ORDER,
    PackageError,
    _is_package_file,
    package_files,
    tree_digest,
)


INDEX_SCHEMA = "koschei.registry-index/v1"

MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
MAX_INDEX_BYTES = 1024 * 1024
MAX_FILES = 1000
MAX_FILE_BYTES = 1024 * 1024
FETCH_TIMEOUT = 30


# --- archives ---------------------------------------------------------------


def build_archive(package_root: Path) -> bytes:
    """A deterministic tar of the package's sources: same files, same bytes."""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for relative in package_files(package_root):
            content = (package_root / relative).read_bytes()
            info = tarfile.TarInfo(relative)
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def extract_archive(data: bytes, destination: Path) -> None:
    """Extract only regular package files; refuse anything else in the tar."""

    if len(data) > MAX_ARCHIVE_BYTES:
        raise PackageError("package archive is larger than 5 MiB")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    except tarfile.TarError as error:
        raise PackageError(f"package archive is not a tar file: {error}") from error
    with archive:
        members = archive.getmembers()
        if len(members) > MAX_FILES:
            raise PackageError("package archive has too many files")
        seen: set[str] = set()
        for member in members:
            name = member.name
            path = PurePosixPath(name)
            if (
                not member.isreg()
                or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or name in seen
                or not _is_package_file(Path(name))
                or member.size > MAX_FILE_BYTES
            ):
                raise PackageError(f"package archive holds a refused entry: {name!r}")
            seen.add(name)
            source = archive.extractfile(member)
            assert source is not None
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(member.size + 1)[: member.size])


# --- index ------------------------------------------------------------------


def archive_path(name: str, version: str) -> str:
    return f"archives/{name}/{name}-{version}.tar"


def _empty_index(name: str) -> dict[str, Any]:
    return {"schema": INDEX_SCHEMA, "name": name, "versions": []}


def validate_index(payload: Any, name: str) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != INDEX_SCHEMA
        or payload.get("name") != name
        or not isinstance(payload.get("versions"), list)
    ):
        raise PackageError(f"registry index for {name!r} has an unknown format")
    seen = set()
    for entry in payload["versions"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("version"), str)
            or not VERSION.fullmatch(entry["version"])
            or entry["version"] in seen
            or not isinstance(entry.get("digest"), str)
            or not DIGEST.fullmatch(entry["digest"])
            or not isinstance(entry.get("archive_sha256"), str)
            or not DIGEST.fullmatch(entry["archive_sha256"])
            or not isinstance(entry.get("surface"), list)
            or any(item not in SURFACE_ORDER for item in entry["surface"])
            or not isinstance(entry.get("dependencies"), dict)
            or not all(
                isinstance(dep, str) and PACKAGE_NAME.fullmatch(dep)
                and isinstance(ver, str) and VERSION.fullmatch(ver)
                for dep, ver in entry["dependencies"].items()
            )
            or not isinstance(entry.get("yanked"), bool)
        ):
            raise PackageError(f"registry index for {name!r} has a malformed version entry")
        seen.add(entry["version"])
    return payload


# --- fetching ---------------------------------------------------------------


def _local_registry(url: str) -> Path | None:
    if url.startswith("file://"):
        return Path(url[len("file://"):])
    return None


def _get(url: str, relative: str, limit: int) -> bytes:
    local = _local_registry(url)
    if local is not None:
        path = local / relative
        if not path.is_file():
            raise PackageError(f"registry has no {relative}")
        data = path.read_bytes()
    else:
        if not url.startswith("https://"):
            raise PackageError("registry URL must be https:// (or file:// for a local registry)")
        request = urllib.request.Request(
            f"{url.rstrip('/')}/{relative}", headers={"User-Agent": "koschei-pkg/1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                data = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise PackageError(f"registry has no {relative}") from error
            raise PackageError(f"registry request failed: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise PackageError(f"registry is unreachable: {error}") from error
    if len(data) > limit:
        raise PackageError(f"registry file {relative} is too large")
    return data


def fetch_index(url: str, name: str) -> dict[str, Any]:
    raw = _get(url, f"index/{name}.json", MAX_INDEX_BYTES)
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PackageError(f"registry index for {name!r} is not JSON") from error
    return validate_index(payload, name)


def fetch_package(url: str, name: str, version: str, destination: Path, *, locked_digest: str | None) -> dict[str, Any]:
    """Download, check and extract one version; return its index entry.

    A yanked version is installed only when the lock already holds exactly it.
    """

    index = fetch_index(url, name)
    entry = next((item for item in index["versions"] if item["version"] == version), None)
    if entry is None:
        raise PackageError(f"registry has no {name} {version}")
    if entry["yanked"] and entry["digest"] != locked_digest:
        raise PackageError(f"{name} {version} is yanked; choose another version")
    data = _get(url, archive_path(name, version), MAX_ARCHIVE_BYTES)
    actual = hashlib.sha256(data).hexdigest()
    if actual != entry["archive_sha256"]:
        raise PackageError(f"{name} {version}: archive SHA-256 {actual[:16]}… does not match the index")
    extract_archive(data, destination)
    digest = tree_digest(destination)
    if digest != entry["digest"]:
        raise PackageError(f"{name} {version}: package digest does not match the index")
    return entry


# --- publishing -------------------------------------------------------------


def _similar(a: str, b: str) -> bool:
    if a == b:
        return False
    normal = lambda text: text.replace("-", "_")
    if normal(a) == normal(b):
        return True
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]:
            return True
        return False
    short, long = sorted((a, b), key=len)
    if len(long) - len(short) != 1:
        return False
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


@dataclass(frozen=True, slots=True)
class Published:
    name: str
    version: str
    surface: tuple[str, ...]
    digest: str
    files: tuple[str, ...]


def publish(package_root: str | Path, registry_dir: str | Path, *, allow_similar_name: bool = False) -> Published:
    """Check a package and add it to a registry checkout. Never overwrites."""

    from .packages_v1 import _package_manifest, inspect_standalone

    package_root = Path(package_root).resolve()
    registry_dir = Path(registry_dir).resolve()
    data_name = _read_name(package_root)
    name, version, _, dependencies, _ = _package_manifest(package_root, data_name)
    if not VERSION.fullmatch(version):
        raise PackageError(f"{name}: version {version!r} must be MAJOR.MINOR.PATCH")
    for dep in dependencies.values():
        if dep.version is None:
            raise PackageError(
                f"{name}: dependency {dep.name!r} must come from the registry "
                "(version = \"x.y.z\") to be published"
            )
    index_dir = registry_dir / "index"
    index_file = index_dir / f"{name}.json"
    if index_file.exists():
        index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
    else:
        index = _empty_index(name)
        existing = sorted(path.stem for path in index_dir.glob("*.json")) if index_dir.is_dir() else []
        close = [other for other in existing if _similar(name, other)]
        if close and not allow_similar_name:
            raise PackageError(
                f"new name {name!r} is close to {', '.join(close)}; names one edit apart are "
                "held for review (pass --allow-similar-name after review)"
            )
    if any(entry["version"] == version for entry in index["versions"]):
        raise PackageError(f"{name} {version} is already published; versions are immutable")

    surface, digest = inspect_standalone(package_root, name, registry_url=f"file://{registry_dir}")
    archive = build_archive(package_root)
    entry = {
        "version": version,
        "digest": digest,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "surface": list(surface),
        "dependencies": {dep.name: dep.version for dep in dependencies.values()},
        "yanked": False,
        "published": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    target = registry_dir / archive_path(name, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive)
    index["versions"].append(entry)
    index_dir.mkdir(parents=True, exist_ok=True)
    _write_json(index_file, index)
    return Published(name, version, surface, digest, (archive_path(name, version), f"index/{name}.json"))


def yank(registry_dir: str | Path, name: str, version: str, *, undo: bool = False) -> None:
    index_file = Path(registry_dir) / "index" / f"{name}.json"
    if not index_file.is_file():
        raise PackageError(f"registry has no package {name!r}")
    index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
    for entry in index["versions"]:
        if entry["version"] == version:
            entry["yanked"] = not undo
            _write_json(index_file, index)
            return
    raise PackageError(f"registry has no {name} {version}")


def _read_name(package_root: Path) -> str:
    import tomllib

    try:
        data = tomllib.loads((package_root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PackageError(f"cannot read {package_root / MANIFEST_NAME}: {error}") from error
    name = data.get("package", {}).get("name") if isinstance(data.get("package"), dict) else None
    if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name):
        raise PackageError("package.name is missing or invalid")
    return name


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
