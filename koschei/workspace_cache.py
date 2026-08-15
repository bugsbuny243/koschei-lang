"""Content-addressed immutable cache for locked workspace native builds."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .workspace import WorkspaceError

CACHE_SCHEMA = "koschei.workspace-native-cache.v1"
CACHE_KEY_SCHEMA = "koschei.workspace-native-cache-key.v1"
DEFAULT_CACHE_DIR = ".koschei/cache/workspace-native-v1"
_DIGEST_LENGTH = 64


@dataclass(frozen=True, slots=True)
class GoToolchainIdentity:
    version: str
    goos: str
    goarch: str
    goexperiment: str

    def to_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "goos": self.goos,
            "goarch": self.goarch,
            "goexperiment": self.goexperiment,
            "cgo_enabled": "0",
        }


@dataclass(frozen=True, slots=True)
class WorkspaceCacheIdentity:
    package: str
    module_lock_digest: str
    mir_version: int
    mir_fingerprint: str
    go_source_sha256: str
    toolchain: GoToolchainIdentity

    def key_payload(self) -> dict[str, object]:
        return {
            "schema_version": CACHE_KEY_SCHEMA,
            "package": self.package,
            "module_lock_digest": self.module_lock_digest,
            "mir_version": self.mir_version,
            "mir_fingerprint": self.mir_fingerprint,
            "go_source_sha256": self.go_source_sha256,
            "toolchain": self.toolchain.to_dict(),
        }

    @property
    def cache_key(self) -> str:
        return _digest(self.key_payload())


@dataclass(frozen=True, slots=True)
class WorkspaceCacheResult:
    artifact: Path
    cache_key: str
    artifact_sha256: str
    hit: bool


def detect_go_toolchain(go_binary: str) -> tuple[GoToolchainIdentity, dict[str, str]]:
    environment = _go_environment()
    version = subprocess.run(
        [go_binary, "version"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if version.returncode != 0:
        raise WorkspaceError("cannot identify local Go toolchain")
    env_result = subprocess.run(
        [go_binary, "env", "-json", "GOOS", "GOARCH", "GOEXPERIMENT"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if env_result.returncode != 0:
        raise WorkspaceError("cannot identify Go target environment")
    try:
        payload = json.loads(env_result.stdout)
    except json.JSONDecodeError as error:
        raise WorkspaceError("Go target environment is not valid JSON") from error
    if not isinstance(payload, dict):
        raise WorkspaceError("Go target environment is not an object")
    values = {name: payload.get(name) for name in ("GOOS", "GOARCH", "GOEXPERIMENT")}
    if any(not isinstance(value, str) for value in values.values()):
        raise WorkspaceError("Go target environment is incomplete")
    return (
        GoToolchainIdentity(
            version=version.stdout.strip(),
            goos=values["GOOS"],
            goarch=values["GOARCH"],
            goexperiment=values["GOEXPERIMENT"],
        ),
        environment,
    )


def build_or_load_cached_native(
    *,
    cache_root: str | Path,
    identity: WorkspaceCacheIdentity,
    go_binary: str,
    go_source: str,
    go_environment: dict[str, str],
) -> WorkspaceCacheResult:
    requested_root = Path(cache_root)
    if requested_root.is_symlink():
        raise WorkspaceError("workspace native cache root cannot be a symlink")
    root = requested_root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)

    cache_key = identity.cache_key
    entry = root / cache_key
    if entry.exists() or entry.is_symlink():
        artifact_sha256 = verify_cache_entry(entry, identity)
        return WorkspaceCacheResult(
            artifact=entry / "artifact",
            cache_key=cache_key,
            artifact_sha256=artifact_sha256,
            hit=True,
        )

    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as temporary:
        build_dir = Path(temporary)
        staged_artifact = build_dir / "artifact"
        (build_dir / "main.go").write_text(go_source, encoding="utf-8")
        (build_dir / "go.mod").write_text(
            "module koscheiworkspaceprogram\n\ngo 1.21\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                go_binary,
                "build",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags=-buildid=",
                "-o",
                str(staged_artifact),
                ".",
            ],
            cwd=build_dir,
            capture_output=True,
            text=True,
            check=False,
            env=go_environment,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or "unknown Go compiler error"
            raise WorkspaceError(
                "workspace native compilation failed; this is a Koschei compiler bug: "
                + details
            )
        artifact_sha256 = hashlib.sha256(staged_artifact.read_bytes()).hexdigest()
        manifest_payload = {
            "schema_version": CACHE_SCHEMA,
            "cache_key": cache_key,
            "identity": identity.key_payload(),
            "artifact": "artifact",
            "artifact_sha256": artifact_sha256,
        }

        try:
            entry.mkdir(mode=0o755)
        except FileExistsError:
            existing_digest = verify_cache_entry(entry, identity)
            return WorkspaceCacheResult(
                artifact=entry / "artifact",
                cache_key=cache_key,
                artifact_sha256=existing_digest,
                hit=True,
            )

        try:
            _copy_create_only(staged_artifact, entry / "artifact", mode=0o755)
            _write_create_only_json(entry / "manifest.json", manifest_payload)
            _fsync_directory(entry)
            _fsync_directory(root)
        except Exception:
            shutil.rmtree(entry, ignore_errors=True)
            raise

    verified = verify_cache_entry(entry, identity)
    return WorkspaceCacheResult(
        artifact=entry / "artifact",
        cache_key=cache_key,
        artifact_sha256=verified,
        hit=False,
    )


def verify_cache_entry(entry: str | Path, identity: WorkspaceCacheIdentity) -> str:
    root = Path(entry)
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError("workspace native cache entry is not a real directory")
    manifest = root / "manifest.json"
    artifact = root / "artifact"
    if manifest.is_symlink() or artifact.is_symlink():
        raise WorkspaceError("workspace native cache entry contains a symlink")
    if not manifest.is_file() or not artifact.is_file():
        raise WorkspaceError("workspace native cache entry is incomplete")
    extras = sorted(
        path.name
        for path in root.iterdir()
        if path.name not in {"manifest.json", "artifact"}
    )
    if extras:
        raise WorkspaceError("workspace native cache entry contains unexpected files")

    try:
        payload = json.loads(
            manifest.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except WorkspaceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("workspace native cache manifest is invalid") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "cache_key",
        "identity",
        "artifact",
        "artifact_sha256",
    }:
        raise WorkspaceError("workspace native cache manifest has unsupported fields")
    if payload["schema_version"] != CACHE_SCHEMA:
        raise WorkspaceError("unsupported workspace native cache schema")
    if payload["artifact"] != "artifact":
        raise WorkspaceError("workspace native cache artifact name mismatch")
    if payload["identity"] != identity.key_payload():
        raise WorkspaceError("workspace native cache identity mismatch")
    if payload["cache_key"] != identity.cache_key:
        raise WorkspaceError("workspace native cache key mismatch")
    if root.name != identity.cache_key:
        raise WorkspaceError("workspace native cache directory key mismatch")
    expected_sha = payload["artifact_sha256"]
    if not _is_digest(expected_sha):
        raise WorkspaceError("workspace native cache artifact digest is invalid")
    observed_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if observed_sha != expected_sha:
        raise WorkspaceError("workspace native cache artifact digest mismatch")
    return observed_sha


def publish_cached_artifact(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise WorkspaceError("cached workspace artifact is unavailable")
    target.parent.mkdir(parents=True, exist_ok=True)
    _copy_create_only(source, target, mode=0o755)


def _go_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["CGO_ENABLED"] = "0"
    environment["GOFLAGS"] = ""
    environment["GOENV"] = "off"
    environment["GOTOOLCHAIN"] = "local"
    return environment


def _copy_create_only(source: Path, destination: Path, *, mode: int) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise WorkspaceError(f"destination already exists: {destination}") from None
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_create_only_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise WorkspaceError(f"destination already exists: {path}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError(f"duplicate workspace cache JSON member: {key}")
        result[key] = value
    return result
