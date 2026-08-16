"""Atomic epoch rotation for authenticated Native Reality object graphs."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from .native_reality_graph_v1 import (
    MAX_GRAPH_BYTES,
    GraphObject,
    NativeRealityGraphProject,
    _build_loaded_module_graph,
    _decode_capsule,
    _encode_capsule,
    _graph_alias,
    load_native_reality_graph_project,
)
from .native_reality_v1 import (
    MAX_SOURCE_BYTES,
    NativeReality,
    _absolute_no_symlink_resolution,
    _encode,
    _exclusive_reality_transition,
    _fresh_nonzero,
    _load_from_handles,
    _open_existing_layout,
    _read_regular_at,
    _replace_sealed_at,
    _require_secure_platform,
    _seal_key,
    _unlink_at,
    _write_exclusive_at,
)

_ALIAS_BYTES = 16


def _fresh_source_write(
    matter_fd: int,
    *,
    source_bytes: bytes,
    reserved_alias: str,
    used: set[str],
) -> str:
    for _ in range(64):
        alias = _fresh_nonzero(_ALIAS_BYTES).hex()
        if alias == reserved_alias or alias in used:
            continue
        try:
            _write_exclusive_at(matter_fd, alias, source_bytes)
        except FileExistsError:
            continue
        used.add(alias)
        return alias
    raise RuntimeError("unable to allocate fresh graph source alias")


def rotate_native_reality_graph_epoch(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
) -> NativeRealityGraphProject:
    """Rotate every physical graph/source alias as one authenticated epoch.

    Canonical project id, object ids, artifact digests and dependency semantics
    remain stable. The HMAC-authenticated reality envelope is the commit point.
    """

    _require_secure_platform()
    _seal_key(seal_key)
    root = _absolute_no_symlink_resolution(path)
    next_project_id: bytes | None = None
    next_epoch: int | None = None

    with _open_existing_layout(root) as (_, reality_fd, matter_fd):
        with _exclusive_reality_transition(reality_fd):
            current = _load_from_handles(
                root,
                reality_fd,
                matter_fd,
                seal_key=seal_key,
                expected_project_id=expected_project_id,
                expected_epoch=expected_epoch,
            )
            reality = current.reality
            if reality.epoch >= (1 << 64) - 1:
                raise ValueError("graph epoch counter exhausted")

            current_capsule_alias = _graph_alias(
                seal_key,
                reality.project_id,
                reality.epoch,
            )
            capsule = _read_regular_at(
                matter_fd,
                current_capsule_alias,
                label="authenticated graph capsule",
                max_bytes=MAX_GRAPH_BYTES,
            )
            objects, edges = _decode_capsule(
                capsule,
                seal_key=seal_key,
                expected_project_id=reality.project_id,
                expected_epoch=reality.epoch,
                expected_root_object_id=reality.root_object_id,
                expected_root_artifact_digest=reality.artifact_digest,
            )
            root_object = next(
                item for item in objects if item.object_id == reality.root_object_id
            )
            if not hmac.compare_digest(
                root_object.epoch_alias,
                reality.epoch_alias,
            ):
                raise ValueError("graph root alias does not match reality envelope")

            # Parse and resolve every current source/edge before creating the next
            # epoch. This rejects hidden edges, cycles and malformed source first.
            _build_loaded_module_graph(
                root=root,
                matter_fd=matter_fd,
                seal_key=seal_key,
                reality=current,
                objects=objects,
                edges=edges,
            )

            source_by_id: dict[bytes, bytes] = {}
            for item in objects:
                source_bytes = _read_regular_at(
                    matter_fd,
                    item.alias_text,
                    label="graph source object",
                    max_bytes=MAX_SOURCE_BYTES,
                )
                if not hmac.compare_digest(
                    hashlib.sha256(source_bytes).digest(),
                    item.artifact_digest,
                ):
                    raise ValueError("graph source changed during epoch rotation")
                source_by_id[item.object_id] = source_bytes

            next_epoch = reality.epoch + 1
            next_capsule_alias = _graph_alias(
                seal_key,
                reality.project_id,
                next_epoch,
            )
            used: set[str] = {next_capsule_alias}
            new_aliases: list[str] = []
            next_objects: list[GraphObject] = []
            capsule_written = False
            switched = False

            try:
                for item in objects:
                    alias = _fresh_source_write(
                        matter_fd,
                        source_bytes=source_by_id[item.object_id],
                        reserved_alias=next_capsule_alias,
                        used=used,
                    )
                    new_aliases.append(alias)
                    next_objects.append(
                        GraphObject(
                            object_id=item.object_id,
                            artifact_digest=item.artifact_digest,
                            epoch_alias=bytes.fromhex(alias),
                        )
                    )

                os.fsync(matter_fd)
                next_objects_tuple = tuple(
                    sorted(next_objects, key=lambda item: item.object_id)
                )
                next_capsule = _encode_capsule(
                    seal_key=seal_key,
                    project_id=reality.project_id,
                    epoch=next_epoch,
                    root_object_id=reality.root_object_id,
                    root_artifact_digest=reality.artifact_digest,
                    objects=next_objects_tuple,
                    edges=edges,
                )
                _write_exclusive_at(
                    matter_fd,
                    next_capsule_alias,
                    next_capsule,
                )
                capsule_written = True
                os.fsync(matter_fd)

                next_root = next(
                    item
                    for item in next_objects_tuple
                    if item.object_id == reality.root_object_id
                )
                next_reality = NativeReality(
                    project_id=reality.project_id,
                    root_object_id=reality.root_object_id,
                    policy_digest=reality.policy_digest,
                    artifact_digest=reality.artifact_digest,
                    epoch=next_epoch,
                    epoch_alias=next_root.epoch_alias,
                )
                _replace_sealed_at(
                    reality_fd,
                    _encode(next_reality, seal_key=seal_key),
                )
                switched = True
            finally:
                if not switched:
                    for alias in new_aliases:
                        try:
                            _unlink_at(matter_fd, alias)
                        except OSError:
                            pass
                    if capsule_written:
                        try:
                            _unlink_at(matter_fd, next_capsule_alias)
                        except OSError:
                            pass
                    try:
                        os.fsync(matter_fd)
                    except OSError:
                        pass

            # New reality is authoritative. Cleanup failure can leave stale
            # physical remnants but cannot make old aliases authoritative again.
            for item in objects:
                try:
                    _unlink_at(matter_fd, item.alias_text)
                except OSError:
                    pass
            try:
                _unlink_at(matter_fd, current_capsule_alias)
            except OSError:
                pass
            try:
                os.fsync(matter_fd)
            except OSError:
                pass

            next_project_id = reality.project_id

    assert next_project_id is not None and next_epoch is not None
    return load_native_reality_graph_project(
        root,
        seal_key=seal_key,
        expected_project_id=next_project_id,
        expected_epoch=next_epoch,
    )
