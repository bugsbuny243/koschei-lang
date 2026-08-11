"""Deterministic SHA-256 lockfiles for Koschei module graphs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .modules import ModuleGraph, check_graph, load_graph

_SCHEMA = "koschei.module-lock.v1"
_DIGEST_LENGTH = 64


class ModuleLockError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class LockedModule:
    path: str
    sha256: str
    imports: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "imports": dict(sorted(self.imports.items())),
        }


@dataclass(frozen=True)
class ModuleLock:
    entrypoint: str
    modules: tuple[LockedModule, ...]
    lock_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "entrypoint": self.entrypoint,
            "modules": [module.to_dict() for module in self.modules],
            "lock_digest": self.lock_digest,
        }


def build_module_lock(
    source: str | Path,
    *,
    graph: ModuleGraph | None = None,
    root: str | Path | None = None,
) -> ModuleLock:
    source_path = Path(source).resolve()
    module_graph = graph if graph is not None else load_graph(source_path)
    check_graph(module_graph)
    lock_root = Path(root).resolve() if root is not None else source_path.parent
    modules: list[LockedModule] = []

    for module in module_graph.modules.values():
        relative = _relative_module_path(lock_root, module.path)
        imports = {
            name: _relative_module_path(lock_root, module_graph.module_of(target).path)
            for name, target in module.imports.items()
        }
        modules.append(
            LockedModule(
                path=relative,
                sha256=hashlib.sha256(module.path.read_bytes()).hexdigest(),
                imports=dict(sorted(imports.items())),
            )
        )

    ordered = tuple(sorted(modules, key=lambda item: item.path))
    entrypoint = _relative_module_path(lock_root, source_path)
    payload = _lock_payload(entrypoint, ordered)
    return ModuleLock(
        entrypoint=entrypoint,
        modules=ordered,
        lock_digest=_digest(payload),
    )


def load_module_lock(path: str | Path) -> ModuleLock:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ModuleLockError("KS1901", "lockfile is not valid JSON") from error
    return _parse_lock(payload)


def verify_module_lock(
    source: str | Path,
    locked: ModuleLock,
    *,
    graph: ModuleGraph | None = None,
    root: str | Path | None = None,
) -> ModuleLock:
    current = build_module_lock(source, graph=graph, root=root)
    if current.entrypoint != locked.entrypoint:
        raise ModuleLockError(
            "KS1904",
            f"entrypoint changed: expected {locked.entrypoint}, found {current.entrypoint}",
        )

    expected = {module.path: module for module in locked.modules}
    actual = {module.path: module for module in current.modules}
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    if missing or added:
        details = []
        if missing:
            details.append("missing modules: " + ", ".join(missing))
        if added:
            details.append("new modules: " + ", ".join(added))
        raise ModuleLockError("KS1904", "; ".join(details))

    for path in sorted(expected):
        before = expected[path]
        after = actual[path]
        if before.imports != after.imports:
            raise ModuleLockError("KS1904", f"import graph changed for {path}")
        if before.sha256 != after.sha256:
            raise ModuleLockError("KS1903", f"module digest changed for {path}")

    if current.lock_digest != locked.lock_digest:
        raise ModuleLockError("KS1903", "module graph digest changed")
    return current


def write_module_lock(
    lock: ModuleLock,
    path: str | Path,
    *,
    replace: bool = False,
) -> None:
    destination = Path(path)
    if destination.exists() and not replace:
        raise ModuleLockError(
            "KS1905",
            f"lockfile already exists: {destination}; use --force to replace it",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(lock.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _parse_lock(payload: Any) -> ModuleLock:
    if not isinstance(payload, dict):
        raise ModuleLockError("KS1901", "lockfile must be a JSON object")
    if set(payload) != {"schema_version", "entrypoint", "modules", "lock_digest"}:
        raise ModuleLockError("KS1901", "lockfile contains unsupported fields")
    if payload["schema_version"] != _SCHEMA:
        raise ModuleLockError("KS1901", "unsupported lockfile schema")

    entrypoint = _validate_relative_path(payload["entrypoint"], "entrypoint")
    raw_modules = payload["modules"]
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ModuleLockError("KS1901", "lockfile modules must be a non-empty array")

    modules: list[LockedModule] = []
    for raw in raw_modules:
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "imports"}:
            raise ModuleLockError("KS1901", "locked module contains unsupported fields")
        path = _validate_relative_path(raw["path"], "module path")
        digest = raw["sha256"]
        if not _is_digest(digest):
            raise ModuleLockError("KS1901", f"invalid SHA-256 digest for {path}")
        imports = raw["imports"]
        if not isinstance(imports, dict):
            raise ModuleLockError("KS1901", f"imports for {path} must be an object")
        normalized_imports: dict[str, str] = {}
        for name, target in imports.items():
            if not isinstance(name, str) or not name:
                raise ModuleLockError("KS1901", f"invalid import name in {path}")
            normalized_imports[name] = _validate_relative_path(target, "import target")
        modules.append(
            LockedModule(
                path=path,
                sha256=digest,
                imports=dict(sorted(normalized_imports.items())),
            )
        )

    ordered = tuple(sorted(modules, key=lambda item: item.path))
    paths = [module.path for module in ordered]
    if len(paths) != len(set(paths)):
        raise ModuleLockError("KS1901", "lockfile contains duplicate module paths")
    if entrypoint not in set(paths):
        raise ModuleLockError("KS1901", "entrypoint is missing from locked modules")
    known = set(paths)
    for module in ordered:
        unknown = sorted(set(module.imports.values()) - known)
        if unknown:
            raise ModuleLockError(
                "KS1901",
                f"{module.path} imports unlocked modules: {', '.join(unknown)}",
            )

    digest = payload["lock_digest"]
    if not _is_digest(digest):
        raise ModuleLockError("KS1901", "invalid lock_digest")
    expected_digest = _digest(_lock_payload(entrypoint, ordered))
    if digest != expected_digest:
        raise ModuleLockError("KS1903", "lockfile digest does not match its module graph")
    return ModuleLock(entrypoint=entrypoint, modules=ordered, lock_digest=digest)


def _lock_payload(
    entrypoint: str,
    modules: tuple[LockedModule, ...],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "entrypoint": entrypoint,
        "modules": [module.to_dict() for module in modules],
    }


def _relative_module_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise ModuleLockError(
            "KS1902",
            f"module escapes the project root: {resolved}",
        ) from error
    return _validate_relative_path(relative.as_posix(), "module path")


def _validate_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModuleLockError("KS1901", f"{label} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".ks":
        raise ModuleLockError("KS1902", f"unsafe {label}: {value}")
    return path.as_posix()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
