"""Authenticated multi-object graph for Koschei Native Reality.

Logical import names exist only inside authorized source views and process memory.
Persistent graph metadata stores keyed import-slot tags, random object identities,
artifact digests and opaque epoch aliases. No semantic filename is authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import struct
from typing import Mapping

from .lexer import LexerError
from .modules import Module, ModuleError, ModuleGraph
from .native_reality_v1 import (
    MAX_SOURCE_BYTES,
    MATTER_DIR_NAME,
    POLICY_DIGEST_V1,
    REALITY_DIR_NAME,
    REALITY_FILE_NAME,
    NativeReality,
    NativeRealityError,
    NativeRealityProject,
    _absolute_no_symlink_resolution,
    _encode,
    _fresh_nonzero,
    _load_from_handles,
    _open_directory_at,
    _open_directory_path,
    _open_existing_layout,
    _read_regular_at,
    _require_bytes,
    _require_secure_platform,
    _safe_remove_created_root,
    _seal_key,
    _source_bytes,
    _unlink_at,
    _write_exclusive_at,
)
from .parser import ParserError, parse

GRAPH_MAGIC = b"KOSCHEI_GRAPH\x00\x00\x00"
GRAPH_SCHEMA_VERSION = 1
MAX_GRAPH_BYTES = 4 << 20
MAX_GRAPH_OBJECTS = 4096
MAX_GRAPH_EDGES = 16384

_ID_BYTES = 16
_DIGEST_BYTES = 32
_ALIAS_BYTES = 16
_GRAPH_HEADER = struct.Struct(">16sB7x16sQ16s32sII")
_OBJECT_RECORD = struct.Struct(">16s32s16s")
_EDGE_RECORD = struct.Struct(">16s32s16s32s")
_SEAL_BYTES = 32

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_GRAPH_SEAL_CONTEXT = b"koschei.graph-seal-key/v1\x00"
_GRAPH_ALIAS_CONTEXT = b"koschei.graph-capsule-alias/v1\x00"
_SLOT_CONTEXT = b"koschei.graph-import-slot/v1\x00"


class NativeRealityGraphError(NativeRealityError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _gfail(code: str, message: str) -> None:
    raise NativeRealityGraphError(code, message)


@dataclass(frozen=True, slots=True)
class GraphObject:
    object_id: bytes
    artifact_digest: bytes
    epoch_alias: bytes

    @property
    def object_id_hex(self) -> str:
        return self.object_id.hex()

    @property
    def alias_text(self) -> str:
        return self.epoch_alias.hex()


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_object_id: bytes
    slot_tag: bytes
    to_object_id: bytes
    expected_artifact_digest: bytes


@dataclass(frozen=True, slots=True)
class NativeRealityGraphProject:
    reality_project: NativeRealityProject
    graph_alias: str
    objects: tuple[GraphObject, ...]
    edges: tuple[GraphEdge, ...]
    module_graph: ModuleGraph


def _graph_key(seal_key: bytes, project_id: bytes) -> bytes:
    key = _seal_key(seal_key)
    project = _require_bytes(project_id, _ID_BYTES, "project_id")
    return hmac.new(key, _GRAPH_SEAL_CONTEXT + project, hashlib.sha256).digest()


def _graph_alias(seal_key: bytes, project_id: bytes, epoch: int) -> str:
    key = _seal_key(seal_key)
    project = _require_bytes(project_id, _ID_BYTES, "project_id")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _gfail("KS5710", "graph epoch must be a positive integer")
    tag = hmac.new(
        key,
        _GRAPH_ALIAS_CONTEXT + project + epoch.to_bytes(8, "big"),
        hashlib.sha256,
    ).digest()
    return tag[:_ALIAS_BYTES].hex()


def _slot_tag(
    seal_key: bytes,
    project_id: bytes,
    from_object_id: bytes,
    import_name: str,
) -> bytes:
    key = _seal_key(seal_key)
    project = _require_bytes(project_id, _ID_BYTES, "project_id")
    source = _require_bytes(from_object_id, _ID_BYTES, "from_object_id")
    if (
        not isinstance(import_name, str)
        or not import_name
        or "\x00" in import_name
    ):
        _gfail("KS5711", "import slot name is not canonical")
    encoded = import_name.encode("utf-8")
    if len(encoded) > 65535:
        _gfail("KS5711", "import slot name is too large")
    payload = (
        _SLOT_CONTEXT
        + project
        + source
        + len(encoded).to_bytes(2, "big")
        + encoded
    )
    return hmac.new(key, payload, hashlib.sha256).digest()


def _canonical_objects(
    objects: tuple[GraphObject, ...],
) -> tuple[GraphObject, ...]:
    return tuple(sorted(objects, key=lambda item: item.object_id))


def _canonical_edges(
    edges: tuple[GraphEdge, ...],
) -> tuple[GraphEdge, ...]:
    return tuple(sorted(edges, key=lambda item: (item.from_object_id, item.slot_tag)))


def _validate_objects(
    objects: tuple[GraphObject, ...],
    *,
    graph_alias: str | None = None,
) -> dict[bytes, GraphObject]:
    if not objects or len(objects) > MAX_GRAPH_OBJECTS:
        _gfail(
            "KS5712",
            f"graph object count must be 1..{MAX_GRAPH_OBJECTS}",
        )
    by_id: dict[bytes, GraphObject] = {}
    aliases: set[bytes] = set()
    reserved = bytes.fromhex(graph_alias) if graph_alias is not None else None
    for item in objects:
        if not isinstance(item, GraphObject):
            _gfail("KS5712", "graph object record type is invalid")
        object_id = _require_bytes(item.object_id, _ID_BYTES, "object_id")
        digest = _require_bytes(
            item.artifact_digest,
            _DIGEST_BYTES,
            "artifact_digest",
        )
        alias = _require_bytes(item.epoch_alias, _ALIAS_BYTES, "epoch_alias")
        if object_id in by_id:
            _gfail("KS5712", "duplicate graph object id")
        if alias in aliases:
            _gfail("KS5712", "duplicate graph epoch alias")
        if reserved is not None and hmac.compare_digest(alias, reserved):
            _gfail("KS5712", "source alias collides with graph capsule alias")
        normalized = GraphObject(object_id, digest, alias)
        by_id[object_id] = normalized
        aliases.add(alias)
    return by_id


def _validate_edges(
    edges: tuple[GraphEdge, ...],
    objects: Mapping[bytes, GraphObject],
) -> dict[tuple[bytes, bytes], GraphEdge]:
    if len(edges) > MAX_GRAPH_EDGES:
        _gfail(
            "KS5713",
            f"graph edge count exceeds {MAX_GRAPH_EDGES}",
        )
    by_slot: dict[tuple[bytes, bytes], GraphEdge] = {}
    for edge in edges:
        if not isinstance(edge, GraphEdge):
            _gfail("KS5713", "graph edge record type is invalid")
        source = _require_bytes(
            edge.from_object_id,
            _ID_BYTES,
            "from_object_id",
        )
        slot = _require_bytes(edge.slot_tag, _DIGEST_BYTES, "slot_tag")
        target = _require_bytes(edge.to_object_id, _ID_BYTES, "to_object_id")
        expected = _require_bytes(
            edge.expected_artifact_digest,
            _DIGEST_BYTES,
            "expected_artifact_digest",
        )
        if source not in objects or target not in objects:
            _gfail("KS5713", "graph edge references an unknown object id")
        if not hmac.compare_digest(objects[target].artifact_digest, expected):
            _gfail(
                "KS5713",
                "graph edge target digest does not match object record",
            )
        key = (source, slot)
        if key in by_slot:
            _gfail("KS5713", "duplicate keyed import slot")
        by_slot[key] = GraphEdge(source, slot, target, expected)
    return by_slot


def _encode_capsule(
    *,
    seal_key: bytes,
    project_id: bytes,
    epoch: int,
    root_object_id: bytes,
    root_artifact_digest: bytes,
    objects: tuple[GraphObject, ...],
    edges: tuple[GraphEdge, ...],
) -> bytes:
    project = _require_bytes(project_id, _ID_BYTES, "project_id")
    root = _require_bytes(root_object_id, _ID_BYTES, "root_object_id")
    root_digest = _require_bytes(
        root_artifact_digest,
        _DIGEST_BYTES,
        "root_artifact_digest",
    )
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        _gfail("KS5710", "graph epoch must be positive")

    alias = _graph_alias(seal_key, project, epoch)
    by_id = _validate_objects(objects, graph_alias=alias)
    _validate_edges(edges, by_id)
    if root not in by_id:
        _gfail("KS5714", "graph root object is absent")
    if not hmac.compare_digest(by_id[root].artifact_digest, root_digest):
        _gfail("KS5714", "graph root digest does not match reality root")

    canonical_objects = _canonical_objects(objects)
    canonical_edges = _canonical_edges(edges)
    body = bytearray(
        _GRAPH_HEADER.pack(
            GRAPH_MAGIC,
            GRAPH_SCHEMA_VERSION,
            project,
            epoch,
            root,
            root_digest,
            len(canonical_objects),
            len(canonical_edges),
        )
    )
    for item in canonical_objects:
        body.extend(
            _OBJECT_RECORD.pack(
                item.object_id,
                item.artifact_digest,
                item.epoch_alias,
            )
        )
    for edge in canonical_edges:
        body.extend(
            _EDGE_RECORD.pack(
                edge.from_object_id,
                edge.slot_tag,
                edge.to_object_id,
                edge.expected_artifact_digest,
            )
        )
    if len(body) + _SEAL_BYTES > MAX_GRAPH_BYTES:
        _gfail("KS5715", "graph capsule exceeds byte budget")
    seal = hmac.new(
        _graph_key(seal_key, project),
        bytes(body),
        hashlib.sha256,
    ).digest()
    return bytes(body) + seal


def _decode_capsule(
    payload: bytes,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    expected_root_object_id: bytes,
    expected_root_artifact_digest: bytes,
) -> tuple[tuple[GraphObject, ...], tuple[GraphEdge, ...]]:
    project = _require_bytes(
        expected_project_id,
        _ID_BYTES,
        "expected_project_id",
    )
    root = _require_bytes(
        expected_root_object_id,
        _ID_BYTES,
        "expected_root_object_id",
    )
    root_digest = _require_bytes(
        expected_root_artifact_digest,
        _DIGEST_BYTES,
        "expected_root_artifact_digest",
    )
    if (
        not isinstance(payload, bytes)
        or len(payload) < _GRAPH_HEADER.size + _SEAL_BYTES
        or len(payload) > MAX_GRAPH_BYTES
    ):
        _gfail("KS5715", "graph capsule size is invalid")

    body, seal = payload[:-_SEAL_BYTES], payload[-_SEAL_BYTES:]
    expected_seal = hmac.new(
        _graph_key(seal_key, project),
        body,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_seal, seal):
        _gfail("KS5716", "graph capsule authentication failed")

    (
        magic,
        version,
        capsule_project,
        epoch,
        capsule_root,
        capsule_root_digest,
        object_count,
        edge_count,
    ) = _GRAPH_HEADER.unpack_from(body, 0)
    if magic != GRAPH_MAGIC or version != GRAPH_SCHEMA_VERSION:
        _gfail("KS5715", "graph capsule schema is invalid")
    if not hmac.compare_digest(capsule_project, project):
        _gfail("KS5716", "graph capsule project context mismatch")
    if (
        not isinstance(expected_epoch, int)
        or isinstance(expected_epoch, bool)
        or expected_epoch < 1
        or epoch != expected_epoch
    ):
        _gfail("KS5716", "graph capsule epoch context mismatch")
    if not hmac.compare_digest(capsule_root, root):
        _gfail("KS5714", "graph capsule root id mismatch")
    if not hmac.compare_digest(capsule_root_digest, root_digest):
        _gfail("KS5714", "graph capsule root digest mismatch")
    if object_count < 1 or object_count > MAX_GRAPH_OBJECTS:
        _gfail("KS5712", "graph object count is invalid")
    if edge_count > MAX_GRAPH_EDGES:
        _gfail("KS5713", "graph edge count is invalid")

    expected_size = (
        _GRAPH_HEADER.size
        + object_count * _OBJECT_RECORD.size
        + edge_count * _EDGE_RECORD.size
    )
    if len(body) != expected_size:
        _gfail("KS5715", "graph capsule count/length mismatch")

    offset = _GRAPH_HEADER.size
    objects_list: list[GraphObject] = []
    for _ in range(object_count):
        object_id, digest, alias = _OBJECT_RECORD.unpack_from(body, offset)
        offset += _OBJECT_RECORD.size
        objects_list.append(GraphObject(object_id, digest, alias))
    edges_list: list[GraphEdge] = []
    for _ in range(edge_count):
        source, slot, target, digest = _EDGE_RECORD.unpack_from(body, offset)
        offset += _EDGE_RECORD.size
        edges_list.append(GraphEdge(source, slot, target, digest))

    objects = tuple(objects_list)
    edges = tuple(edges_list)
    if objects != _canonical_objects(objects):
        _gfail("KS5715", "graph object records are not canonical")
    if edges != _canonical_edges(edges):
        _gfail("KS5715", "graph edge records are not canonical")
    alias = _graph_alias(seal_key, project, expected_epoch)
    by_id = _validate_objects(objects, graph_alias=alias)
    _validate_edges(edges, by_id)
    if root not in by_id:
        _gfail("KS5714", "graph root object is absent")
    if not hmac.compare_digest(by_id[root].artifact_digest, root_digest):
        _gfail("KS5714", "graph root object digest mismatch")
    return objects, edges


def _validate_source_labels(sources: Mapping[str, str], root_label: str) -> None:
    if not isinstance(sources, Mapping) or not sources:
        _gfail("KS5717", "sources must be a non-empty mapping")
    if len(sources) > MAX_GRAPH_OBJECTS:
        _gfail("KS5717", "too many source objects")
    for label, source_text in sources.items():
        if not isinstance(label, str) or not _LABEL_RE.fullmatch(label):
            _gfail("KS5717", f"source label is not a canonical identifier: {label!r}")
        _source_bytes(source_text)
    if root_label not in sources:
        _gfail("KS5717", "root label is absent from sources")


def _parse_sources(
    sources: Mapping[str, str],
) -> dict[str, object]:
    programs: dict[str, object] = {}
    for label, source_text in sources.items():
        try:
            program = parse(source_text)
        except (LexerError, ParserError):
            raise
        seen: set[str] = set()
        for declaration in program.imports:
            if declaration.name in seen:
                raise ModuleError(
                    "KS1603",
                    f"'{declaration.name}' module is imported more than once.",
                    declaration.location,
                )
            seen.add(declaration.name)
            if declaration.name not in sources:
                raise ModuleError(
                    "KS1601",
                    f"Authenticated graph target is missing for import '{declaration.name}'.",
                    declaration.location,
                )
        programs[label] = program
    return programs


def _validate_label_topology(
    *,
    programs: Mapping[str, object],
    root_label: str,
) -> None:
    state: dict[str, int] = {}
    trail: list[str] = []
    reachable: set[str] = set()

    def visit(label: str) -> None:
        status = state.get(label, 0)
        if status == 2:
            reachable.add(label)
            return
        if status == 1:
            cycle = trail[trail.index(label):] + [label]
            _gfail(
                "KS5718",
                "authenticated object graph contains a cycle: "
                + " -> ".join(cycle),
            )
        state[label] = 1
        reachable.add(label)
        trail.append(label)
        try:
            for declaration in programs[label].imports:
                visit(declaration.name)
        finally:
            trail.pop()
        state[label] = 2

    visit(root_label)
    unreachable = sorted(set(programs) - reachable)
    if unreachable:
        _gfail(
            "KS5718",
            "authenticated object graph contains unreachable source objects",
        )


def _allocate_aliases(
    *,
    seal_key: bytes,
    project_id: bytes,
    epoch: int,
    labels: tuple[str, ...],
) -> dict[str, bytes]:
    reserved = bytes.fromhex(_graph_alias(seal_key, project_id, epoch))
    aliases: dict[str, bytes] = {}
    used = {reserved}
    for label in labels:
        for _ in range(32):
            alias = _fresh_nonzero(_ALIAS_BYTES)
            if alias not in used:
                aliases[label] = alias
                used.add(alias)
                break
        else:
            _gfail("KS5712", "unable to allocate unique opaque source alias")
    return aliases


def _build_records(
    *,
    seal_key: bytes,
    project_id: bytes,
    sources: Mapping[str, str],
    programs: Mapping[str, object],
    object_ids: Mapping[str, bytes],
    aliases: Mapping[str, bytes],
) -> tuple[tuple[GraphObject, ...], tuple[GraphEdge, ...]]:
    objects_by_label: dict[str, GraphObject] = {}
    for label, source_text in sources.items():
        digest = hashlib.sha256(_source_bytes(source_text)).digest()
        objects_by_label[label] = GraphObject(
            object_id=object_ids[label],
            artifact_digest=digest,
            epoch_alias=aliases[label],
        )

    edges: list[GraphEdge] = []
    for label, program in programs.items():
        source_id = object_ids[label]
        for declaration in program.imports:
            target = objects_by_label[declaration.name]
            edges.append(
                GraphEdge(
                    from_object_id=source_id,
                    slot_tag=_slot_tag(
                        seal_key,
                        project_id,
                        source_id,
                        declaration.name,
                    ),
                    to_object_id=target.object_id,
                    expected_artifact_digest=target.artifact_digest,
                )
            )
    return (
        _canonical_objects(tuple(objects_by_label.values())),
        _canonical_edges(tuple(edges)),
    )


def _remove_created_layout(
    *,
    root_fd: int | None,
    reality_fd: int | None,
    matter_fd: int | None,
    source_aliases: tuple[str, ...],
    graph_alias: str | None,
    graph_written: bool,
    created_reality: bool,
    created_matter: bool,
) -> None:
    if matter_fd is not None:
        for alias in source_aliases:
            try:
                _unlink_at(matter_fd, alias)
            except OSError:
                pass
        if graph_written and graph_alias is not None:
            try:
                _unlink_at(matter_fd, graph_alias)
            except OSError:
                pass
    if reality_fd is not None:
        try:
            _unlink_at(reality_fd, REALITY_FILE_NAME)
        except OSError:
            pass
    if matter_fd is not None:
        os.close(matter_fd)
    if reality_fd is not None:
        if created_matter:
            try:
                os.rmdir(MATTER_DIR_NAME, dir_fd=reality_fd)
            except OSError:
                pass
        os.close(reality_fd)
    if root_fd is not None and created_reality:
        try:
            os.rmdir(REALITY_DIR_NAME, dir_fd=root_fd)
        except OSError:
            pass


def create_native_reality_graph_project(
    destination: str | Path,
    *,
    seal_key: bytes,
    sources: Mapping[str, str],
    root_label: str,
) -> NativeRealityGraphProject:
    """Create a multi-object project without persisting logical source labels."""

    _require_secure_platform()
    _seal_key(seal_key)
    _validate_source_labels(sources, root_label)
    programs = _parse_sources(sources)

    project_id = _fresh_nonzero(_ID_BYTES)
    labels = tuple(sorted(sources))
    object_ids: dict[str, bytes] = {}
    used_ids: set[bytes] = set()
    for label in labels:
        while True:
            object_id = _fresh_nonzero(_ID_BYTES)
            if object_id not in used_ids:
                object_ids[label] = object_id
                used_ids.add(object_id)
                break
    _validate_label_topology(programs=programs, root_label=root_label)
    aliases = _allocate_aliases(
        seal_key=seal_key,
        project_id=project_id,
        epoch=1,
        labels=labels,
    )
    objects, edges = _build_records(
        seal_key=seal_key,
        project_id=project_id,
        sources=sources,
        programs=programs,
        object_ids=object_ids,
        aliases=aliases,
    )
    root_object = next(
        item for item in objects if item.object_id == object_ids[root_label]
    )
    capsule_alias = _graph_alias(seal_key, project_id, 1)
    capsule = _encode_capsule(
        seal_key=seal_key,
        project_id=project_id,
        epoch=1,
        root_object_id=root_object.object_id,
        root_artifact_digest=root_object.artifact_digest,
        objects=objects,
        edges=edges,
    )
    reality = NativeReality(
        project_id=project_id,
        root_object_id=root_object.object_id,
        policy_digest=POLICY_DIGEST_V1,
        artifact_digest=root_object.artifact_digest,
        epoch=1,
        epoch_alias=root_object.epoch_alias,
    )

    root = _absolute_no_symlink_resolution(destination)
    existed = root.exists() or root.is_symlink()
    if not existed:
        root.mkdir(parents=True, mode=0o700)

    root_fd: int | None = None
    reality_fd: int | None = None
    matter_fd: int | None = None
    root_identity: tuple[int, int] | None = None
    success = False
    written_aliases: list[str] = []
    created_reality = False
    created_matter = False
    graph_written = False
    try:
        root_fd = _open_directory_path(root, "project root")
        root_info = os.fstat(root_fd)
        root_identity = (root_info.st_dev, root_info.st_ino)
        if os.listdir(root_fd):
            _gfail("KS5719", f"destination is not empty: {root}")
        os.mkdir(REALITY_DIR_NAME, 0o700, dir_fd=root_fd)
        created_reality = True
        reality_fd = _open_directory_at(root_fd, REALITY_DIR_NAME, "reality root")
        os.mkdir(MATTER_DIR_NAME, 0o700, dir_fd=reality_fd)
        created_matter = True
        matter_fd = _open_directory_at(reality_fd, MATTER_DIR_NAME, "matter root")

        label_by_id = {object_ids[label]: label for label in labels}
        for item in objects:
            label = label_by_id[item.object_id]
            alias_text = item.alias_text
            _write_exclusive_at(
                matter_fd,
                alias_text,
                _source_bytes(sources[label]),
            )
            written_aliases.append(alias_text)
        _write_exclusive_at(matter_fd, capsule_alias, capsule)
        graph_written = True
        os.fsync(matter_fd)
        _write_exclusive_at(
            reality_fd,
            REALITY_FILE_NAME,
            _encode(reality, seal_key=seal_key),
        )
        os.fsync(reality_fd)
        os.fsync(root_fd)
        success = True
    except Exception:
        _remove_created_layout(
            root_fd=root_fd,
            reality_fd=reality_fd,
            matter_fd=matter_fd,
            source_aliases=tuple(written_aliases),
            graph_alias=capsule_alias,
            graph_written=graph_written,
            created_reality=created_reality,
            created_matter=created_matter,
        )
        root_fd = reality_fd = matter_fd = None
        if not existed and root_identity is not None:
            _safe_remove_created_root(root, root_identity)
        raise
    finally:
        if matter_fd is not None:
            os.close(matter_fd)
        if reality_fd is not None:
            os.close(reality_fd)
        if root_fd is not None:
            os.close(root_fd)

    if not success:
        _gfail("KS5719", "graph project creation did not complete")
    return load_native_reality_graph_project(
        root,
        seal_key=seal_key,
        expected_project_id=project_id,
        expected_epoch=1,
    )


def _build_loaded_module_graph(
    *,
    root: Path,
    matter_fd: int,
    seal_key: bytes,
    reality: NativeRealityProject,
    objects: tuple[GraphObject, ...],
    edges: tuple[GraphEdge, ...],
) -> ModuleGraph:
    by_id = {item.object_id: item for item in objects}
    edge_by_slot = {
        (edge.from_object_id, edge.slot_tag): edge
        for edge in edges
    }
    modules: dict[str, Module] = {}
    programs: dict[bytes, object] = {}
    used_edges: set[tuple[bytes, bytes]] = set()

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
            _gfail("KS5720", "graph source object hash mismatch")
        try:
            text = source_bytes.decode("utf-8")
        except UnicodeError as error:
            raise NativeRealityGraphError(
                "KS5720",
                f"graph source object is not UTF-8: {error}",
            ) from error
        source_path = root / REALITY_DIR_NAME / MATTER_DIR_NAME / item.alias_text
        try:
            program = parse(text)
        except (LexerError, ParserError) as error:
            error.source_path = source_path
            raise
        programs[item.object_id] = program
        key = "koschei-object:" + item.object_id_hex
        modules[key] = Module(
            name=item.object_id_hex,
            path=source_path,
            program=program,
        )

    for item in objects:
        key = "koschei-object:" + item.object_id_hex
        module = modules[key]
        seen_names: set[str] = set()
        for declaration in programs[item.object_id].imports:
            if declaration.name in seen_names:
                raise ModuleError(
                    "KS1603",
                    f"'{declaration.name}' module is imported more than once.",
                    declaration.location,
                )
            seen_names.add(declaration.name)
            slot = _slot_tag(
                seal_key,
                reality.reality.project_id,
                item.object_id,
                declaration.name,
            )
            edge_key = (item.object_id, slot)
            edge = edge_by_slot.get(edge_key)
            if edge is None:
                raise ModuleError(
                    "KS5626",
                    f"Import '{declaration.name}' has no authenticated object edge.",
                    declaration.location,
                )
            target = by_id[edge.to_object_id]
            if not hmac.compare_digest(
                edge.expected_artifact_digest,
                target.artifact_digest,
            ):
                _gfail("KS5713", "edge digest changed during load")
            module.imports[declaration.name] = (
                "koschei-object:" + target.object_id_hex
            )
            used_edges.add(edge_key)

    if len(used_edges) != len(edges):
        _gfail(
            "KS5721",
            "authenticated graph contains edge slots not present in source imports",
        )

    root_key = "koschei-object:" + reality.reality.root_object_id_hex
    graph = ModuleGraph(root=root_key, modules=modules)
    _validate_loaded_topology(graph)
    return graph


def _validate_loaded_topology(graph: ModuleGraph) -> None:
    state: dict[str, int] = {}
    trail: list[str] = []
    reachable: set[str] = set()

    def visit(key: str) -> None:
        status = state.get(key, 0)
        if status == 2:
            reachable.add(key)
            return
        if status == 1:
            cycle = trail[trail.index(key):] + [key]
            _gfail(
                "KS5718",
                "authenticated loaded graph contains a dependency cycle: "
                + " -> ".join(item.rsplit(":", 1)[-1] for item in cycle),
            )
        state[key] = 1
        reachable.add(key)
        trail.append(key)
        try:
            for target in graph.modules[key].imports.values():
                visit(target)
        finally:
            trail.pop()
        state[key] = 2

    visit(graph.root)
    if reachable != set(graph.modules):
        _gfail(
            "KS5718",
            "authenticated loaded graph contains unreachable source objects",
        )


def load_native_reality_graph_project(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
) -> NativeRealityGraphProject:
    """Authenticate and load all graph objects without filename resolution."""

    _require_secure_platform()
    _seal_key(seal_key)
    root = _absolute_no_symlink_resolution(path)
    with _open_existing_layout(root) as (_, reality_fd, matter_fd):
        reality = _load_from_handles(
            root,
            reality_fd,
            matter_fd,
            seal_key=seal_key,
            expected_project_id=expected_project_id,
            expected_epoch=expected_epoch,
        )
        capsule_alias = _graph_alias(
            seal_key,
            reality.reality.project_id,
            reality.reality.epoch,
        )
        capsule = _read_regular_at(
            matter_fd,
            capsule_alias,
            label="authenticated graph capsule",
            max_bytes=MAX_GRAPH_BYTES,
        )
        objects, edges = _decode_capsule(
            capsule,
            seal_key=seal_key,
            expected_project_id=reality.reality.project_id,
            expected_epoch=reality.reality.epoch,
            expected_root_object_id=reality.reality.root_object_id,
            expected_root_artifact_digest=reality.reality.artifact_digest,
        )
        root_object = next(
            item
            for item in objects
            if item.object_id == reality.reality.root_object_id
        )
        if not hmac.compare_digest(
            root_object.epoch_alias,
            reality.reality.epoch_alias,
        ):
            _gfail("KS5714", "graph root alias does not match reality envelope")
        module_graph = _build_loaded_module_graph(
            root=root,
            matter_fd=matter_fd,
            seal_key=seal_key,
            reality=reality,
            objects=objects,
            edges=edges,
        )
        return NativeRealityGraphProject(
            reality_project=reality,
            graph_alias=capsule_alias,
            objects=objects,
            edges=edges,
            module_graph=module_graph,
        )
