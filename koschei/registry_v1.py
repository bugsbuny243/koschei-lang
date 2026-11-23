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

SIGNER = re.compile(r"^ed25519:[0-9a-f]{64}$")
SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
SIGNATURE_CONTEXT = b"koschei-package-signature/v1\n"
LOG_NAME = "log.jsonl"
GENESIS = "0" * 64
MAX_LOG_BYTES = 50 * 1024 * 1024
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
            or ("signer" in entry) != ("signature" in entry)
            or ("signer" in entry and not _valid_signer(entry["signer"]))
            or ("signature" in entry and not (
                isinstance(entry["signature"], str) and SIGNATURE.fullmatch(entry["signature"])
            ))
        ):
            raise PackageError(f"registry index for {name!r} has a malformed version entry")
        seen.add(entry["version"])
    owners = payload.get("owners", [])
    if not isinstance(owners, list) or not all(_valid_signer(owner) for owner in owners):
        raise PackageError(f"registry index for {name!r} has malformed owners")
    return payload


# --- signatures -------------------------------------------------------------


def _valid_signer(value: Any) -> bool:
    return isinstance(value, str) and bool(SIGNER.fullmatch(value))


def signed_message(name: str, entry: dict[str, Any]) -> bytes:
    """The bytes a publisher signs: everything that identifies the release."""

    payload = {
        "name": name,
        "version": entry["version"],
        "digest": entry["digest"],
        "archive_sha256": entry["archive_sha256"],
        "surface": entry["surface"],
        "dependencies": entry["dependencies"],
    }
    return SIGNATURE_CONTEXT + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def check_signature(name: str, entry: dict[str, Any], owners: list[str]) -> str | None:
    """Return the entry's signer after verifying it, or None if unsigned."""

    from .ed25519_v1 import verify

    signer = entry.get("signer")
    if signer is None:
        return None
    if owners and signer not in owners:
        raise PackageError(f"{name} {entry['version']} is signed by {signer[:24]}…, not by an owner")
    public = bytes.fromhex(signer.split(":", 1)[1])
    if not verify(public, signed_message(name, entry), bytes.fromhex(entry["signature"])):
        raise PackageError(f"{name} {entry['version']}: the signature does not verify")
    return signer


def load_key(path: str | Path) -> tuple[bytes, str]:
    """Read a key file written by ``ks pkg keygen``: (seed, "ed25519:<public>")."""

    from .ed25519_v1 import public_key

    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise PackageError(f"cannot read key file: {error}") from error
    match = re.fullmatch(r"koschei-ed25519-secret:([0-9a-f]{64})", text)
    if not match:
        raise PackageError("not a Koschei key file (expected koschei-ed25519-secret:<64 hex>)")
    seed = bytes.fromhex(match.group(1))
    return seed, "ed25519:" + public_key(seed).hex()


def keygen(path: str | Path) -> str:
    from .ed25519_v1 import new_seed, public_key

    target = Path(path)
    if target.exists():
        raise PackageError(f"{target} already exists; refusing to overwrite a key")
    seed = new_seed()
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"koschei-ed25519-secret:{seed.hex()}\n")
    return "ed25519:" + public_key(seed).hex()


def _sign_entry(name: str, entry: dict[str, Any], seed: bytes, signer: str) -> None:
    from .ed25519_v1 import sign

    entry["signer"] = signer
    entry["signature"] = sign(seed, signed_message(name, entry)).hex()


# --- public log ---------------------------------------------------------------
#
# registry/log.jsonl is append-only: each line records one publish, sign or
# yank and carries the SHA-256 of the line before it, so rewriting history
# changes every later hash. Clients pin the head they have seen.


def _line_hash(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def parse_log(data: bytes) -> list[dict[str, Any]]:
    if data and not data.endswith(b"\n"):
        raise PackageError("registry log is truncated")
    events: list[dict[str, Any]] = []
    previous = GENESIS
    for number, line in enumerate(data.splitlines(keepends=True)):
        try:
            event = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise PackageError(f"registry log line {number + 1} is not JSON") from error
        if (
            not isinstance(event, dict)
            or type(event.get("seq")) is not int
            or event.get("seq") != number
            or event.get("prev") != previous
            or event.get("event") not in {"publish", "sign", "yank", "unyank"}
            or not isinstance(event.get("name"), str)
            or not isinstance(event.get("version"), str)
        ):
            raise PackageError(f"registry log line {number + 1} breaks the chain")
        event["_hash"] = _line_hash(line)
        events.append(event)
        previous = event["_hash"]
    return events


def _append_log(registry_dir: Path, event: dict[str, Any]) -> None:
    path = registry_dir / LOG_NAME
    data = path.read_bytes() if path.exists() else b""
    events = parse_log(data)
    record = {
        "seq": len(events),
        "prev": events[-1]["_hash"] if events else GENESIS,
        **event,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with path.open("ab") as handle:
        handle.write(line)


def _log_event(event: str, name: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": event,
        "name": name,
        "version": entry["version"],
        "digest": entry["digest"],
        "archive_sha256": entry["archive_sha256"],
        "signer": entry.get("signer"),
        "signature": entry.get("signature"),
    }


def check_log(events: list[dict[str, Any]], name: str, entry: dict[str, Any], pinned: dict[str, Any] | None) -> dict[str, Any]:
    """The entry must match the log's latest record of it; history must extend ``pinned``."""

    if pinned is not None:
        seq, expected = pinned["seq"], pinned["hash"]
        if seq >= len(events) or events[seq]["_hash"] != expected:
            raise PackageError(
                "the registry log no longer contains the history this project saw "
                f"(entry {seq}); refusing to trust the registry"
            )
    latest = None
    for event in events:
        if event["name"] == name and event["version"] == entry["version"] and event["event"] in {"publish", "sign"}:
            latest = event
    if latest is None:
        raise PackageError(f"{name} {entry['version']} is not in the registry's public log")
    for key in ("digest", "archive_sha256", "signer", "signature"):
        if latest.get(key) != entry.get(key):
            raise PackageError(f"{name} {entry['version']}: index and public log disagree on {key}")
    return {"seq": len(events) - 1, "hash": events[-1]["_hash"]}


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


def fetch_log(url: str) -> list[dict[str, Any]]:
    return parse_log(_get(url, LOG_NAME, MAX_LOG_BYTES))


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
    return dict(entry, _owners=list(index.get("owners", [])))


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


def publish(
    package_root: str | Path,
    registry_dir: str | Path,
    *,
    key: str | Path,
    allow_similar_name: bool = False,
) -> Published:
    """Check, sign and add a package to a registry checkout. Never overwrites."""

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
    seed, signer = load_key(key)
    owners = index.setdefault("owners", [])
    if owners and signer not in owners:
        raise PackageError(
            f"{signer[:24]}… is not an owner of {name}; an owner must add the key to "
            "the index's owners in a reviewed pull request"
        )

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
    _sign_entry(name, entry, seed, signer)
    if not owners:
        owners.append(signer)
    target = registry_dir / archive_path(name, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive)
    index["versions"].append(entry)
    index_dir.mkdir(parents=True, exist_ok=True)
    _write_json(index_file, index)
    _append_log(registry_dir, _log_event("publish", name, entry))
    return Published(
        name, version, surface, digest,
        (archive_path(name, version), f"index/{name}.json", LOG_NAME),
    )


def sign_existing(registry_dir: str | Path, name: str, version: str, *, key: str | Path) -> str:
    """Sign a version published before signatures existed. A signature is never replaced."""

    registry_dir = Path(registry_dir).resolve()
    index_file = registry_dir / "index" / f"{name}.json"
    if not index_file.is_file():
        raise PackageError(f"registry has no package {name!r}")
    index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
    seed, signer = load_key(key)
    owners = index.setdefault("owners", [])
    if owners and signer not in owners:
        raise PackageError(f"{signer[:24]}… is not an owner of {name}")
    for entry in index["versions"]:
        if entry["version"] == version:
            if "signature" in entry:
                raise PackageError(f"{name} {version} is already signed; signatures are never replaced")
            # Sign what the archive actually holds, not only what the index says.
            data = (registry_dir / archive_path(name, version)).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["archive_sha256"]:
                raise PackageError(f"{name} {version}: archive does not match the index; not signing")
            _sign_entry(name, entry, seed, signer)
            if not owners:
                owners.append(signer)
            _write_json(index_file, index)
            _append_log(registry_dir, _log_event("sign", name, entry))
            return signer
    raise PackageError(f"registry has no {name} {version}")


def yank(registry_dir: str | Path, name: str, version: str, *, undo: bool = False) -> None:
    index_file = Path(registry_dir) / "index" / f"{name}.json"
    if not index_file.is_file():
        raise PackageError(f"registry has no package {name!r}")
    index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
    for entry in index["versions"]:
        if entry["version"] == version:
            entry["yanked"] = not undo
            _write_json(index_file, index)
            _append_log(Path(registry_dir), _log_event("unyank" if undo else "yank", name, entry))
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
