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
from pathlib import Path
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


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AliasRotationError(f"invalid {field}")
    return value


def _require_epoch(epoch: int) -> int:
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise AliasRotationError("epoch must be a non-negative integer")
    return epoch


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
    """Return a new graph payload plus an atomic storage rename plan.

    object_id, artifact_hash, policy_hash, provenance, capabilities and edges are
    preserved byte-for-byte at the data-model level; only epoch_alias changes.
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
        old_alias = _require_text(item.get("epoch_alias"), "epoch_alias")
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
