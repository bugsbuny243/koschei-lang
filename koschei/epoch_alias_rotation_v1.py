"""Epoch-scoped opaque physical aliases for protected Koschei source objects.

Aliases are storage locators only. They are derived with an independent rotation
key supplied by the trusted workspace/storage broker; the key is never an
artifact-encryption key and aliases never become canonical object identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any

SCHEMA = "koschei.opaque-source-graph/v1"
_ALIAS_PREFIX = "K"
_ALIAS_BYTES = 10


class AliasRotationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AliasMove:
    object_id: str
    old_alias: str
    new_alias: str


@dataclass(frozen=True, slots=True)
class StorageRotationResult:
    storage_epoch: int
    moves: tuple[AliasMove, ...]
    graph_path: Path


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AliasRotationError(f"invalid {field}")
    return value


def _require_epoch(epoch: int) -> int:
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise AliasRotationError("epoch must be a non-negative integer")
    return epoch


def _safe_locator(value: str) -> str:
    alias = _require_text(value, "epoch_alias")
    if alias in {".", ".."} or "/" in alias or "\\" in alias:
        raise AliasRotationError("epoch_alias must be an opaque single-path locator")
    if len(alias) < 8:
        raise AliasRotationError("epoch_alias is too short")
    return alias


def derive_epoch_alias(
    *,
    project_id: str,
    object_id: str,
    epoch: int,
    rotation_key: bytes,
    collision_counter: int = 0,
) -> str:
    """Derive an opaque locator without changing canonical object identity."""

    project = _require_text(project_id, "project_id")
    oid = _require_text(object_id, "object_id").lower()
    _require_epoch(epoch)
    if len(oid) < 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise AliasRotationError("object_id must be >=128-bit hexadecimal")
    if not isinstance(rotation_key, bytes) or len(rotation_key) < 32:
        raise AliasRotationError("rotation_key must contain at least 256 bits")
    if not isinstance(collision_counter, int) or collision_counter < 0:
        raise AliasRotationError("collision_counter must be non-negative")

    message = (
        b"koschei/epoch-alias/v1\x00"
        + project.encode("utf-8")
        + b"\x00"
        + oid.encode("ascii")
        + b"\x00"
        + str(epoch).encode("ascii")
        + b"\x00"
        + str(collision_counter).encode("ascii")
    )
    digest = hmac.new(rotation_key, message, hashlib.sha256).digest()[:_ALIAS_BYTES]
    token = base64.b32encode(digest).decode("ascii").rstrip("=")
    return _ALIAS_PREFIX + token


def rotate_graph_payload(
    payload: dict[str, Any],
    *,
    epoch: int,
    rotation_key: bytes,
) -> tuple[dict[str, Any], tuple[AliasMove, ...]]:
    """Return a new graph payload plus a storage rename plan.

    object_id, artifact_hash, policy_hash, provenance, capabilities and edges are
    preserved at the data-model level; only epoch_alias and storage_epoch change.
    """

    _require_epoch(epoch)
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise AliasRotationError("unsupported protected graph schema")
    project_id = _require_text(payload.get("project_id"), "project_id")
    raw_objects = payload.get("objects")
    if not isinstance(raw_objects, list) or not raw_objects:
        raise AliasRotationError("graph must contain objects")

    result = json.loads(json.dumps(payload))
    objects = result["objects"]
    used: set[str] = set()
    moves: list[AliasMove] = []

    for item in objects:
        if not isinstance(item, dict):
            raise AliasRotationError("object entry must be an object")
        object_id = _require_text(item.get("object_id"), "object_id").lower()
        old_alias = _safe_locator(_require_text(item.get("epoch_alias"), "epoch_alias"))
        counter = 0
        while True:
            alias = derive_epoch_alias(
                project_id=project_id,
                object_id=object_id,
                epoch=epoch,
                rotation_key=rotation_key,
                collision_counter=counter,
            )
            if alias not in used:
                break
            counter += 1
        used.add(alias)
        item["epoch_alias"] = alias
        moves.append(AliasMove(object_id, old_alias, alias))

    result["storage_epoch"] = epoch
    return result, tuple(moves)


def rotate_graph_file(
    graph_path: str | Path,
    *,
    epoch: int,
    rotation_key: bytes,
) -> tuple[dict[str, Any], tuple[AliasMove, ...]]:
    path = Path(graph_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AliasRotationError(f"graph read failed: {error}") from error
    return rotate_graph_payload(payload, epoch=epoch, rotation_key=rotation_key)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preflight_moves(object_store: Path, moves: tuple[AliasMove, ...]) -> dict[str, str]:
    if not object_store.is_dir():
        raise AliasRotationError("object_store must be an existing directory")

    old_aliases: set[str] = set()
    new_aliases: set[str] = set()
    hashes: dict[str, str] = {}

    for move in moves:
        old_alias = _safe_locator(move.old_alias)
        new_alias = _safe_locator(move.new_alias)
        if old_alias in old_aliases:
            raise AliasRotationError("rotation plan contains duplicate old alias")
        if new_alias in new_aliases:
            raise AliasRotationError("rotation plan contains duplicate new alias")
        old_aliases.add(old_alias)
        new_aliases.add(new_alias)

        source = object_store / old_alias
        if not source.is_file():
            raise AliasRotationError(f"rotation source missing for object {move.object_id}")
        hashes[move.object_id] = _sha256_file(source)

    for move in moves:
        destination = object_store / move.new_alias
        if move.new_alias not in old_aliases and destination.exists():
            raise AliasRotationError(f"rotation destination already exists for object {move.object_id}")

    return hashes


def apply_alias_moves_atomically(
    object_store: str | Path,
    moves: tuple[AliasMove, ...],
) -> None:
    """Apply a cycle-safe two-phase alias rotation with rollback.

    All current aliases are staged to opaque temporary names before any final
    alias is installed. This permits A->B/B->A plans and prevents partial direct
    rename chains from overwriting another canonical object.
    """

    store = Path(object_store).resolve()
    expected_hashes = _preflight_moves(store, moves)
    token = secrets.token_hex(16)
    staged: dict[str, Path] = {}
    finalised: set[str] = set()

    try:
        for index, move in enumerate(moves):
            source = store / move.old_alias
            temporary = store / f"KROTATE{token}{index:08x}"
            if temporary.exists():
                raise AliasRotationError("rotation temporary locator collision")
            os.replace(source, temporary)
            staged[move.object_id] = temporary

        for move in moves:
            temporary = staged[move.object_id]
            destination = store / move.new_alias
            os.replace(temporary, destination)
            finalised.add(move.object_id)

        for move in moves:
            destination = store / move.new_alias
            if not destination.is_file():
                raise AliasRotationError("rotation verification lost a destination object")
            if _sha256_file(destination) != expected_hashes[move.object_id]:
                raise AliasRotationError("rotation verification changed object bytes")
    except Exception as error:
        rollback_errors: list[str] = []
        for move in reversed(moves):
            try:
                current = store / move.new_alias if move.object_id in finalised else staged.get(move.object_id)
                if current is not None and current.exists():
                    os.replace(current, store / move.old_alias)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise AliasRotationError(
                "rotation failed and rollback was incomplete: " + "; ".join(rollback_errors)
            ) from error
        if isinstance(error, AliasRotationError):
            raise
        raise AliasRotationError(f"rotation failed and was rolled back: {error}") from error


def rotate_object_store_atomically(
    graph_path: str | Path,
    object_store: str | Path,
    *,
    epoch: int,
    rotation_key: bytes,
) -> StorageRotationResult:
    """Rotate physical aliases and atomically publish the matching graph payload.

    Storage is rotated first with rollback support. The graph is written to a
    sibling temporary file, fsynced, and atomically replaced only after storage
    verification succeeds. If graph publication fails, storage aliases are
    rolled back to the admitted graph's old aliases.
    """

    graph = Path(graph_path).resolve()
    store = Path(object_store).resolve()
    try:
        payload = json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AliasRotationError(f"graph read failed: {error}") from error

    rotated, moves = rotate_graph_payload(payload, epoch=epoch, rotation_key=rotation_key)
    apply_alias_moves_atomically(store, moves)

    temp_graph = graph.with_name(f".{graph.name}.krotate-{secrets.token_hex(12)}")
    graph_committed = False
    try:
        encoded = (json.dumps(rotated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with temp_graph.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_graph, graph)
        graph_committed = True
    except Exception as error:
        if temp_graph.exists():
            try:
                temp_graph.unlink()
            except OSError:
                pass
        reverse_moves = tuple(
            AliasMove(move.object_id, move.new_alias, move.old_alias)
            for move in moves
        )
        try:
            apply_alias_moves_atomically(store, reverse_moves)
        except Exception as rollback_error:
            raise AliasRotationError(
                f"graph publication failed and storage rollback was incomplete: {rollback_error}"
            ) from error
        raise AliasRotationError(f"graph publication failed; storage rolled back: {error}") from error

    if not graph_committed:
        raise AliasRotationError("rotation graph publication did not commit")
    return StorageRotationResult(storage_epoch=epoch, moves=moves, graph_path=graph)
