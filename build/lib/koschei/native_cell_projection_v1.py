"""Koschei-native sealed cell projection v1.

Projection is not source-level member/index syntax.  The source remains a native
cell reality with multiple resolved witnesses.  Authenticated Object Space
metadata binds the complete schema table plus one selected ordinal/domain.

The whole aggregate is validated before selection.  Only the selected canonical
scalar crosses the frontend boundary, so an unselected malformed cell cannot hide
behind a projection and source/schema/storage identities do not become runtime
member names.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping, Sequence

from . import native_value_domains_v1 as _base
from .ast_nodes import Block, Program, ReturnStatement, SourceLocation
from .generic_nodes import GenericFunctionDeclaration
from .modules import Module, ModuleGraph, check_graph
from .native_cell_realities_v1 import (
    MAX_CELL_COUNT_V1,
    NativeCellRecordV1,
    NativeCellRealityError,
    _CELL,
    _DOMAIN_TO_CODE,
    _CODE_TO_DOMAIN,
    _evaluate_cell_source,
    _parse_cell_source,
    _witness_tag,
)
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, ObjectSpaceError, ObjectSpaceProject
from .semantic import SemanticChecker, SemanticReport


PROJECTION_GRAPH_MAGIC_V1 = b"KOSCHEI_OSPROJ1\x00"
PROJECTION_GRAPH_VERSION_V1 = 1
_PROJECTION_FRONTEND_CONTEXT = b"koschei.frontend/native-cell-projection/v1"
NATIVE_CELL_PROJECTION_FRONTEND_V1 = hashlib.sha256(_PROJECTION_FRONTEND_CONTEXT).digest()

_ID_BYTES = 16
_SCHEMA_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32

# magic, version, project, root, source digest, frontend, schema,
# full-cell-count, selected ordinal, selected domain code
_HEADER = struct.Struct(">16sB7x16s16s32s32s16sHHB5x")


class NativeCellProjectionError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCellProjectionCheckV1:
    schema_id: bytes
    ordered_witnesses: tuple[str, ...]
    dependency_order: tuple[str, ...]
    values: Mapping[str, _base.NativeValue]
    cells: tuple[_base.NativeValue, ...]
    selected_ordinal: int
    selected_value: _base.NativeValue
    lowered: Program
    semantic: SemanticReport


def _fail(message: str) -> None:
    raise NativeCellProjectionError(message)


def _exact(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _source(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        _fail("native cell projection source must be bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NativeCellProjectionError(
            "native cell projection source is not valid UTF-8"
        ) from error


def _validate_cell_names(cell_witnesses: Sequence[str]) -> tuple[str, ...]:
    if (
        not isinstance(cell_witnesses, Sequence)
        or isinstance(cell_witnesses, (str, bytes))
        or not 1 <= len(cell_witnesses) <= MAX_CELL_COUNT_V1
    ):
        _fail(f"cell_witnesses must contain 1..{MAX_CELL_COUNT_V1} entries")
    names = tuple(cell_witnesses)
    if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
        _fail("cell_witnesses must be unique text witness identities")
    return names


def _lower_selected(value: _base.NativeValue) -> tuple[Program, SemanticReport]:
    location = SourceLocation(1, 1)
    origin = GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=_base._type_ref(value.domain, location),
        body=Block((ReturnStatement(_base._lower_value(value, location), location),)),
        location=location,
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    program = Program((origin,))
    semantic = SemanticChecker(program).check()
    return program, semantic


def is_native_cell_projection_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(PROJECTION_GRAPH_MAGIC_V1)


def encode_native_cell_projection_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    schema_id: bytes,
    cell_witnesses: Sequence[str],
    selected_ordinal: int,
) -> bytes:
    project = _exact(project_id, _ID_BYTES, "project id")
    root = _exact(root_object_id, _ID_BYTES, "root object id")
    schema = _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    if not isinstance(objects, Mapping) or set(objects) != {root}:
        _fail("native cell projection v1 requires exactly one authoritative root object")
    names = _validate_cell_names(cell_witnesses)
    if (
        not isinstance(selected_ordinal, int)
        or isinstance(selected_ordinal, bool)
        or not 0 <= selected_ordinal < len(names)
    ):
        _fail("selected cell ordinal is outside the sealed cell schema")

    source_bytes = objects[root]
    try:
        parsed = _parse_cell_source(_source(source_bytes))
        if set(parsed.resolves) != set(names):
            _fail("source resolve set must exactly match sealed projection cell set")
        order, values = _evaluate_cell_source(parsed, names)
    except NativeCellRealityError as error:
        raise NativeCellProjectionError(str(error)) from error
    del order
    digest = hashlib.sha256(source_bytes).digest()

    records: list[NativeCellRecordV1] = []
    seen_tags: set[bytes] = set()
    for ordinal, name in enumerate(names):
        value = values.get(name)
        if value is None:
            _fail(f"sealed projection cell witness {name!r} is unresolved")
        tag = _witness_tag(
            project_id=project,
            root_object_id=root,
            source_digest=digest,
            witness_name=name,
        )
        if tag in seen_tags:
            _fail("projection cell witness tag collision")
        seen_tags.add(tag)
        records.append(NativeCellRecordV1(ordinal, tag, value.domain))

    selected_domain = records[selected_ordinal].domain
    body = bytearray(
        _HEADER.pack(
            PROJECTION_GRAPH_MAGIC_V1,
            PROJECTION_GRAPH_VERSION_V1,
            project,
            root,
            digest,
            NATIVE_CELL_PROJECTION_FRONTEND_V1,
            schema,
            len(records),
            selected_ordinal,
            _DOMAIN_TO_CODE[selected_domain],
        )
    )
    for record in records:
        body.extend(
            _CELL.pack(
                record.ordinal,
                record.witness_tag,
                _DOMAIN_TO_CODE[record.domain],
            )
        )
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("native cell projection graph exceeds sealed graph byte budget")
    return bytes(body)


def decode_native_cell_projection_graph(
    project: ObjectSpaceProject,
) -> NativeCellProjectionCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native cell projection requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size:
        _fail("native cell projection graph is truncated")
    (
        magic,
        version,
        project_id,
        root_id,
        digest,
        frontend,
        schema_id,
        cell_count,
        selected_ordinal,
        selected_domain_code,
    ) = _HEADER.unpack_from(payload, 0)
    if magic != PROJECTION_GRAPH_MAGIC_V1 or version != PROJECTION_GRAPH_VERSION_V1:
        _fail("native cell projection graph schema is invalid")
    if project_id != project.project_id or root_id != project.root_object_id:
        _fail("native cell projection trusted project/root context mismatch")
    if frontend != NATIVE_CELL_PROJECTION_FRONTEND_V1:
        _fail("native cell projection frontend identity mismatch")
    _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    if not 1 <= cell_count <= MAX_CELL_COUNT_V1:
        _fail("native cell projection cell count is outside policy")
    if selected_ordinal >= cell_count:
        _fail("selected cell ordinal is outside the sealed cell schema")
    selected_domain = _CODE_TO_DOMAIN.get(selected_domain_code)
    if selected_domain is None:
        _fail("selected cell domain code is invalid")
    expected_size = _HEADER.size + cell_count * _CELL.size
    if len(payload) != expected_size:
        _fail("native cell projection count/length relation is non-canonical")

    if len(project.records) != 1 or project.records[0].object_id != root_id:
        _fail("native cell projection object set differs from sealed k0 authority")
    if set(project.object_payloads) != {root_id}:
        _fail("opened native cell projection payload set differs from authority")
    if project.records[0].artifact_digest != digest:
        _fail("native cell projection source digest differs from sealed k0 authority")
    source_bytes = project.object_payloads[root_id]
    if hashlib.sha256(source_bytes).digest() != digest:
        _fail("opened projection source digest differs from authenticated authority")

    records: list[NativeCellRecordV1] = []
    offset = _HEADER.size
    for expected_ordinal in range(cell_count):
        ordinal, tag, domain_code = _CELL.unpack_from(payload, offset)
        offset += _CELL.size
        if ordinal != expected_ordinal:
            _fail("native cell projection table is not canonical ordinal order")
        domain = _CODE_TO_DOMAIN.get(domain_code)
        if domain is None:
            _fail("native cell projection cell domain code is invalid")
        records.append(NativeCellRecordV1(ordinal, tag, domain))
    if records[selected_ordinal].domain != selected_domain:
        _fail("selected cell domain contract disagrees with the full sealed schema")

    try:
        parsed = _parse_cell_source(_source(source_bytes))
    except NativeCellRealityError as error:
        raise NativeCellProjectionError(str(error)) from error
    by_tag: dict[bytes, str] = {}
    for name in parsed.resolves:
        tag = _witness_tag(
            project_id=project.project_id,
            root_object_id=root_id,
            source_digest=digest,
            witness_name=name,
        )
        if tag in by_tag:
            _fail("projection witness tag collision during load")
        by_tag[tag] = name

    ordered_names: list[str] = []
    for record in records:
        name = by_tag.get(record.witness_tag)
        if name is None:
            _fail("sealed projection cell does not match any resolved source witness")
        ordered_names.append(name)
    if set(ordered_names) != set(parsed.resolves) or len(ordered_names) != len(parsed.resolves):
        _fail("sealed projection table does not exactly cover source resolve set")

    try:
        order, values = _evaluate_cell_source(parsed, ordered_names)
    except NativeCellRealityError as error:
        raise NativeCellProjectionError(str(error)) from error
    cells: list[_base.NativeValue] = []
    for record, name in zip(records, ordered_names):
        value = values[name]
        if value.domain != record.domain:
            _fail("sealed projection cell domain differs from evaluated source reality")
        cells.append(value)

    selected_value = cells[selected_ordinal]
    if selected_value.domain != selected_domain:
        _fail("selected projection value violates its sealed domain contract")
    lowered, semantic = _lower_selected(selected_value)
    return NativeCellProjectionCheckV1(
        schema_id=schema_id,
        ordered_witnesses=tuple(ordered_names),
        dependency_order=order,
        values=values,
        cells=tuple(cells),
        selected_ordinal=selected_ordinal,
        selected_value=selected_value,
        lowered=lowered,
        semantic=semantic,
    )


def check_native_cell_projection_object_space(project: ObjectSpaceProject):
    checked = decode_native_cell_projection_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-cell-projection-root>",
                path=Path("<koschei-native-cell-projection-root>"),
                program=checked.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
