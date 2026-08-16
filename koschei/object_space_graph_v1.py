"""Canonical dependency graph carried only inside Object Space k0 graph_secret.

The persistent graph never stores logical import/module/file names. During the
legacy grammar migration, an authorized source object may still contain an import
spelling. The sealed graph binds that declaration by ordinal position to a stable
object identity and expected artifact digest.

Semantic identity is the canonical object id. ``Module.path`` is synthetic and is
used only for diagnostics; no sibling filename or path resolver is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping, Sequence

from .ast_nodes import SourceLocation
from .lexer import LexerError
from .modules import Module, ModuleError, ModuleGraph, check_graph
from .object_space_v1 import (
    MAX_GRAPH_SECRET_BYTES,
    MAX_OBJECTS,
    ObjectSpaceError,
    ObjectSpaceProject,
    ObjectSpaceRecord,
)
from .parser import ParserError, parse


_GRAPH_MAGIC = b"KOSCHEI_OSGRAPH1\x00"
_GRAPH_VERSION = 1
_ID_BYTES = 16
_DIGEST_BYTES = 32
MAX_GRAPH_EDGES_V1 = 16384

# magic, version, project id, root object id, object count, edge count
_HEADER = struct.Struct(">16sB7x16s16sII")
_OBJECT = struct.Struct(">16s32s")
# source object id, source import ordinal, target object id, target digest
_EDGE = struct.Struct(">16sI16s32s")


class ObjectSpaceGraphError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class ObjectSpaceGraphEdge:
    source_object_id: bytes
    import_ordinal: int
    target_object_id: bytes
    target_artifact_digest: bytes


def _fail(message: str) -> None:
    raise ObjectSpaceGraphError(message)


def _id(value: object, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != _ID_BYTES or not any(value):
        _fail(f"{label} must be exactly {_ID_BYTES} non-zero bytes")
    return value


def _digest(value: object, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != _DIGEST_BYTES:
        _fail(f"{label} must be exactly {_DIGEST_BYTES} bytes")
    return value


def _decode_source(payload: object, object_id: bytes) -> tuple[str, object]:
    if not isinstance(payload, bytes):
        _fail("graph source payload must be bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise ObjectSpaceGraphError("graph source object is not UTF-8") from error
    synthetic = Path(f"<koschei-object-{object_id.hex()}>")
    try:
        program = parse(text)
    except (LexerError, ParserError) as error:
        error.source_path = synthetic
        raise
    return text, program


def encode_object_space_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    target_by_import_slot: Mapping[bytes, Sequence[bytes]],
) -> bytes:
    """Build canonical graph bytes before sealing them inside k0.

    ``target_by_import_slot[source][n]`` resolves the nth import declaration in
    that source object. Logical import strings are deliberately absent from the
    returned bytes.
    """

    project = _id(project_id, "project id")
    root = _id(root_object_id, "root object id")
    if not isinstance(objects, Mapping) or not objects or len(objects) > MAX_OBJECTS:
        _fail(f"graph object map must contain 1..{MAX_OBJECTS} objects")

    canonical_objects: list[tuple[bytes, bytes]] = []
    programs: dict[bytes, object] = {}
    for raw_id, payload in objects.items():
        object_id = _id(raw_id, "object id")
        if not isinstance(payload, bytes):
            _fail("graph source payload must be bytes")
        canonical_objects.append((object_id, hashlib.sha256(payload).digest()))
        _, programs[object_id] = _decode_source(payload, object_id)
    canonical_objects.sort(key=lambda item: item[0])
    by_id = dict(canonical_objects)
    if root not in by_id:
        _fail("graph root object is absent")

    unknown_sources = set(target_by_import_slot) - set(by_id)
    if unknown_sources:
        _fail("graph slot map contains an unknown source object")

    edges: list[ObjectSpaceGraphEdge] = []
    for object_id, _ in canonical_objects:
        imports = tuple(programs[object_id].imports)
        targets = tuple(target_by_import_slot.get(object_id, ()))
        if len(imports) != len(targets):
            _fail("graph slot count does not exactly match source import declarations")
        if len(set(declaration.name for declaration in imports)) != len(imports):
            _fail("source contains duplicate logical import declarations")
        for ordinal, raw_target in enumerate(targets):
            target = _id(raw_target, "target object id")
            if target not in by_id:
                _fail("graph edge target object is absent")
            edges.append(
                ObjectSpaceGraphEdge(
                    source_object_id=object_id,
                    import_ordinal=ordinal,
                    target_object_id=target,
                    target_artifact_digest=by_id[target],
                )
            )
    if len(edges) > MAX_GRAPH_EDGES_V1:
        _fail(f"graph edge count exceeds {MAX_GRAPH_EDGES_V1}")
    edges.sort(key=lambda edge: (edge.source_object_id, edge.import_ordinal))

    _validate_topology(
        root_object_id=root,
        object_ids=set(by_id),
        edges=tuple(edges),
    )

    body = bytearray(
        _HEADER.pack(
            _GRAPH_MAGIC,
            _GRAPH_VERSION,
            project,
            root,
            len(canonical_objects),
            len(edges),
        )
    )
    for object_id, artifact_digest in canonical_objects:
        body.extend(_OBJECT.pack(object_id, artifact_digest))
    for edge in edges:
        body.extend(
            _EDGE.pack(
                edge.source_object_id,
                edge.import_ordinal,
                edge.target_object_id,
                edge.target_artifact_digest,
            )
        )
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("object-space graph secret exceeds sealed graph byte budget")
    return bytes(body)


def _validate_topology(
    *,
    root_object_id: bytes,
    object_ids: set[bytes],
    edges: tuple[ObjectSpaceGraphEdge, ...],
) -> None:
    outgoing: dict[bytes, list[bytes]] = {object_id: [] for object_id in object_ids}
    seen_slots: set[tuple[bytes, int]] = set()
    for edge in edges:
        if edge.source_object_id not in object_ids or edge.target_object_id not in object_ids:
            _fail("graph edge references an unknown object")
        slot = (edge.source_object_id, edge.import_ordinal)
        if slot in seen_slots:
            _fail("graph contains a duplicate source import slot")
        seen_slots.add(slot)
        outgoing[edge.source_object_id].append(edge.target_object_id)

    visiting: set[bytes] = set()
    visited: set[bytes] = set()

    def visit(object_id: bytes) -> None:
        if object_id in visiting:
            _fail("object-space graph contains a dependency cycle")
        if object_id in visited:
            return
        visiting.add(object_id)
        for target in outgoing[object_id]:
            visit(target)
        visiting.remove(object_id)
        visited.add(object_id)

    visit(root_object_id)
    if visited != object_ids:
        _fail("object-space graph contains unreachable/orphan objects")


def decode_object_space_graph(project: ObjectSpaceProject) -> tuple[tuple[tuple[bytes, bytes], ...], tuple[ObjectSpaceGraphEdge, ...]]:
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size or len(payload) > MAX_GRAPH_SECRET_BYTES:
        _fail("sealed object-space graph length is invalid")
    magic, version, project_id, root_id, object_count, edge_count = _HEADER.unpack_from(payload, 0)
    if magic != _GRAPH_MAGIC or version != _GRAPH_VERSION:
        _fail("sealed object-space graph schema is invalid")
    if project_id != project.project_id:
        _fail("sealed graph belongs to another project")
    if root_id != project.root_object_id:
        _fail("sealed graph root identity mismatch")
    if object_count < 1 or object_count > MAX_OBJECTS:
        _fail("sealed graph object count is outside policy")
    if edge_count > MAX_GRAPH_EDGES_V1:
        _fail("sealed graph edge count is outside policy")
    expected_size = _HEADER.size + object_count * _OBJECT.size + edge_count * _EDGE.size
    if len(payload) != expected_size:
        _fail("sealed graph count/length relation is non-canonical")

    offset = _HEADER.size
    objects: list[tuple[bytes, bytes]] = []
    seen_ids: set[bytes] = set()
    for _ in range(object_count):
        object_id, artifact_digest = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        _id(object_id, "sealed graph object id")
        _digest(artifact_digest, "sealed graph object digest")
        if object_id in seen_ids:
            _fail("sealed graph contains duplicate object identity")
        seen_ids.add(object_id)
        objects.append((object_id, artifact_digest))
    if objects != sorted(objects, key=lambda item: item[0]):
        _fail("sealed graph object table is not canonical")

    record_by_id = {record.object_id: record for record in project.records}
    graph_by_id = dict(objects)
    if set(graph_by_id) != set(record_by_id):
        _fail("sealed graph object set differs from k0 object authority")
    for object_id, graph_digest in objects:
        if graph_digest != record_by_id[object_id].artifact_digest:
            _fail("sealed graph object digest differs from k0 authority")

    edges: list[ObjectSpaceGraphEdge] = []
    seen_slots: set[tuple[bytes, int]] = set()
    for _ in range(edge_count):
        source, ordinal, target, target_digest = _EDGE.unpack_from(payload, offset)
        offset += _EDGE.size
        _id(source, "sealed graph edge source")
        _id(target, "sealed graph edge target")
        _digest(target_digest, "sealed graph edge target digest")
        if source not in graph_by_id or target not in graph_by_id:
            _fail("sealed graph edge references an unknown object")
        slot = (source, ordinal)
        if slot in seen_slots:
            _fail("sealed graph contains a duplicate import slot")
        seen_slots.add(slot)
        if target_digest != graph_by_id[target]:
            _fail("sealed graph edge target digest mismatch")
        edges.append(ObjectSpaceGraphEdge(source, ordinal, target, target_digest))
    if edges != sorted(edges, key=lambda edge: (edge.source_object_id, edge.import_ordinal)):
        _fail("sealed graph edge table is not canonical")

    _validate_topology(root_object_id=root_id, object_ids=set(graph_by_id), edges=tuple(edges))
    return tuple(objects), tuple(edges)


def load_object_space_module_graph(project: ObjectSpaceProject) -> ModuleGraph:
    """Construct compiler ModuleGraph without filesystem/name resolution."""

    objects, edges = decode_object_space_graph(project)
    del objects
    edges_by_source: dict[bytes, dict[int, ObjectSpaceGraphEdge]] = {}
    for edge in edges:
        edges_by_source.setdefault(edge.source_object_id, {})[edge.import_ordinal] = edge

    modules: dict[str, Module] = {}
    key_by_id = {object_id: object_id.hex() for object_id in project.object_payloads}
    for object_id in sorted(project.object_payloads):
        _, program = _decode_source(project.object_payloads[object_id], object_id)
        edge_slots = edges_by_source.get(object_id, {})
        if len(program.imports) != len(edge_slots):
            _fail("sealed graph slots do not exactly match opened source imports")
        imports: dict[str, str] = {}
        for ordinal, declaration in enumerate(program.imports):
            edge = edge_slots.get(ordinal)
            if edge is None:
                _fail("sealed graph is missing a source import slot")
            if declaration.name in imports:
                raise ModuleError(
                    "KS1603",
                    f"duplicate import declaration: {declaration.name}",
                    declaration.location,
                )
            imports[declaration.name] = key_by_id[edge.target_object_id]
        modules[key_by_id[object_id]] = Module(
            name=key_by_id[object_id],
            path=Path(f"<koschei-object-{object_id.hex()}>") ,
            program=program,
            imports=imports,
        )

    root_key = key_by_id[project.root_object_id]
    return ModuleGraph(root=root_key, modules=modules)


def check_object_space_graph(project: ObjectSpaceProject):
    """Run the existing semantic/type/effect/MIR check pipeline on object identity."""

    graph = load_object_space_module_graph(project)
    report = check_graph(graph)
    return graph, report
