"""Koschei-native sealed cell realities v1.

A cell reality is an authenticated, schema-bound ordered aggregate of already
canonical Koschei scalar values.  It intentionally adds no source keyword and
no record/struct/tuple/list/map syntax.

Source uses the native value witness grammar but may contain multiple ``resolve``
clauses.  Their textual order is not schema order.  Sealed metadata binds an
opaque schema id and an ordered list of keyed witness tags; those tags select
which resolved witnesses become cell 0..N-1.

Below the frontend boundary, the verified values are materialized into one
synthetic compatibility struct with local c0/c1/... field names.  The synthetic
shape is an implementation detail: source witness names, schema identity and
Object Space identity do not become runtime field names or public storage
identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence

from . import native_value_domains_v1 as _base
from .ast_nodes import (
    Block,
    Program,
    ReturnStatement,
    SourceLocation,
    StructDeclaration,
    StructField,
    StructLiteral,
    TypeRef,
)
from .generic_nodes import GenericFunctionDeclaration
from .modules import Module, ModuleGraph, check_graph
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, ObjectSpaceError, ObjectSpaceProject
from .semantic import INT_MAX, INT_MIN, SemanticChecker, SemanticReport


CELL_GRAPH_MAGIC_V1 = b"KOSCHEI_OSCELL1\x00"
CELL_GRAPH_VERSION_V1 = 1
_CELL_FRONTEND_CONTEXT = b"koschei.frontend/native-cell-realities/v1"
NATIVE_CELL_FRONTEND_V1 = hashlib.sha256(_CELL_FRONTEND_CONTEXT).digest()

MAX_CELL_COUNT_V1 = 64
_SCHEMA_ID_BYTES = 16
_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32
_TAG_BYTES = 32

# magic, version, project id, root id, source digest, frontend id, schema id,
# cell count
_HEADER = struct.Struct(">16sB7x16s16s32s32s16sH6x")
# ordinal, witness tag, domain code
_CELL = struct.Struct(">H2x32sB7x")

_DOMAIN_TO_CODE = {_base.WHOLE: 1, _base.TRUTH: 2, _base.GLYPHS: 3}
_CODE_TO_DOMAIN = {value: key for key, value in _DOMAIN_TO_CODE.items()}
_TAG_CONTEXT = b"koschei.native-cell.witness-tag/v1\x00"


class NativeCellRealityError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCellSourceV1:
    witnesses: tuple[_base.ValueWitness, ...]
    resolves: tuple[str, ...]
    resolve_locations: Mapping[str, SourceLocation]

    def by_name(self) -> dict[str, _base.ValueWitness]:
        return {item.name: item for item in self.witnesses}


@dataclass(frozen=True, slots=True)
class NativeCellRecordV1:
    ordinal: int
    witness_tag: bytes
    domain: str


@dataclass(frozen=True, slots=True)
class NativeCellRealityCheckV1:
    source: NativeCellSourceV1
    schema_id: bytes
    ordered_witnesses: tuple[str, ...]
    dependency_order: tuple[str, ...]
    values: Mapping[str, _base.NativeValue]
    cells: tuple[_base.NativeValue, ...]
    lowered: Program
    semantic: SemanticReport


def _fail(message: str) -> None:
    raise NativeCellRealityError(message)


def _exact(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _source(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        _fail("native cell source payload must be bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NativeCellRealityError("native cell source payload is not valid UTF-8") from error


def _parse_cell_source(source: str) -> NativeCellSourceV1:
    """Parse native value clauses with a bounded set of unordered resolves."""

    try:
        lines = _base._canonical_lines(source)
    except _base.NativeValueDomainError as error:
        raise NativeCellRealityError(str(error)) from error

    witnesses: list[_base.ValueWitness] = []
    seen_witnesses: set[str] = set()
    resolves: list[str] = []
    resolve_locations: dict[str, SourceLocation] = {}

    for line_number, line in enumerate(lines, start=1):
        tokens = line.split(" ")
        head = tokens[0]
        grammar_prefix = line
        if len(tokens) >= 3 and tokens[0] == "witness" and tokens[2] == "glyphs":
            grammar_prefix = " ".join(tokens[:4]) if len(tokens) >= 4 else line
        for symbol in _base._LEGACY_SYMBOLS:
            if symbol in grammar_prefix:
                _fail(f"legacy punctuation {symbol!r} is not native cell grammar")

        if head == "witness":
            if len(tokens) < 3:
                _fail("witness requires identity and term")
            try:
                name = _base._name(tokens[1], line=line_number)
                term = _base._term(tokens[2:], line=line_number)
            except _base.NativeValueDomainError as error:
                raise NativeCellRealityError(str(error)) from error
            if name in seen_witnesses:
                _fail(f"duplicate witness identity {name!r}")
            seen_witnesses.add(name)
            witnesses.append(
                _base.ValueWitness(name, term, SourceLocation(line_number, 1))
            )
            if len(witnesses) > _base.MAX_VALUE_WITNESSES:
                _fail(f"cell source exceeds {_base.MAX_VALUE_WITNESSES} witnesses")
            continue

        if head == "resolve":
            if len(tokens) != 2:
                _fail("resolve requires exactly one witness identity")
            try:
                name = _base._name(tokens[1], line=line_number)
            except _base.NativeValueDomainError as error:
                raise NativeCellRealityError(str(error)) from error
            if name in resolve_locations:
                _fail(f"duplicate resolved cell witness {name!r}")
            resolves.append(name)
            resolve_locations[name] = SourceLocation(line_number, 1)
            if len(resolves) > MAX_CELL_COUNT_V1:
                _fail(f"cell source exceeds {MAX_CELL_COUNT_V1} resolved cells")
            continue

        if head in _base._LEGACY_WORDS:
            _fail(f"legacy grammar word {head!r} is rejected")
        _fail(f"unknown native cell clause {head!r}")

    if not witnesses:
        _fail("native cell source must contain at least one witness")
    if not resolves:
        _fail("native cell source must resolve at least one cell witness")
    return NativeCellSourceV1(
        tuple(witnesses), tuple(resolves), resolve_locations
    )


def _dependencies(witness: _base.ValueWitness) -> tuple[str, ...]:
    return tuple(atom.witness for atom in witness.term.atoms if atom.witness is not None)


def _multi_dependency_order(
    source: NativeCellSourceV1,
    roots: Sequence[str],
) -> tuple[str, ...]:
    """Iterative union reachability for all sealed cell roots."""

    by_name = source.by_name()
    ordered: list[str] = []
    state: dict[str, int] = {}
    reachable: set[str] = set()

    # Root order cannot change graph validity/evaluation.  Metadata determines
    # aggregate ordinal order separately.
    for root in sorted(set(roots)):
        if root not in by_name:
            _fail(f"resolved cell references unknown witness {root!r}")
        if state.get(root, 0) == 2:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        trail: list[str] = []
        while stack:
            name, index = stack[-1]
            witness = by_name[name]
            if state.get(name, 0) == 0:
                state[name] = 1
                reachable.add(name)
                trail.append(name)
            dependencies = _dependencies(witness)
            if index < len(dependencies):
                dependency = dependencies[index]
                stack[-1] = (name, index + 1)
                target = by_name.get(dependency)
                if target is None:
                    _fail(f"witness {name!r} references unknown witness {dependency!r}")
                mark = state.get(dependency, 0)
                if mark == 1:
                    _fail("native cell source contains a witness cycle")
                if mark == 0:
                    stack.append((dependency, 0))
                else:
                    reachable.add(dependency)
                continue
            stack.pop()
            if trail and trail[-1] == name:
                trail.pop()
            state[name] = 2
            if name not in ordered:
                ordered.append(name)

    dormant = sorted(set(by_name) - reachable)
    if dormant:
        _fail(
            "native cell source contains dormant witnesses outside the sealed cell reality: "
            + ", ".join(dormant)
        )
    return tuple(ordered)


def _evaluate_cell_source(
    source: NativeCellSourceV1,
    roots: Sequence[str],
) -> tuple[tuple[str, ...], dict[str, _base.NativeValue]]:
    order = _multi_dependency_order(source, roots)
    by_name = source.by_name()
    values: dict[str, _base.NativeValue] = {}

    def atom_value(atom: _base.ValueAtom) -> _base.NativeValue:
        if atom.literal is not None:
            return atom.literal
        assert atom.witness is not None
        return values[atom.witness]

    for name in order:
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            value = atom_value(term.atoms[0])
        else:
            left = atom_value(term.atoms[0])
            right = atom_value(term.atoms[1])
            operation = term.operation
            if operation in _base._NUMERIC_OPS:
                if left.domain != _base.WHOLE or right.domain != _base.WHOLE:
                    _fail(f"{operation} requires whole/whole and forbids coercion")
                a = int(left.value)
                b = int(right.value)
                if operation == "sum":
                    result = a + b
                elif operation == "difference":
                    result = a - b
                else:
                    result = a * b
                if not INT_MIN <= result <= INT_MAX:
                    _fail(f"{operation} exceeds signed Int64 reality")
                value = _base.NativeValue(_base.WHOLE, result)
            elif operation == "same":
                if left.domain != right.domain:
                    _fail("same requires identical value domains and forbids coercion")
                value = _base.NativeValue(_base.TRUTH, left.value == right.value)
            elif operation == "merge":
                if left.domain != _base.GLYPHS or right.domain != _base.GLYPHS:
                    _fail("merge requires glyphs/glyphs and forbids textual coercion")
                merged = unicodedata.normalize("NFC", str(left.value) + str(right.value))
                if len(merged.encode("utf-8")) > _base.MAX_GLYPHS_RESULT_BYTES:
                    _fail("merged glyphs exceeds result byte budget")
                value = _base.NativeValue(_base.GLYPHS, merged)
            else:
                _fail(f"unknown native cell operation {operation!r}")
        values[name] = value
    return order, values


def _witness_tag(
    *,
    project_id: bytes,
    root_object_id: bytes,
    source_digest: bytes,
    witness_name: str,
) -> bytes:
    return hashlib.sha256(
        _TAG_CONTEXT
        + project_id
        + root_object_id
        + source_digest
        + witness_name.encode("ascii")
    ).digest()


def _lower_cell_reality(cells: Sequence[_base.NativeValue]) -> tuple[Program, SemanticReport]:
    location = SourceLocation(1, 1)
    type_name = "KCellReality"
    fields = tuple(
        StructField(
            f"c{index}",
            _base._type_ref(value.domain, location),
            location,
        )
        for index, value in enumerate(cells)
    )
    declaration = StructDeclaration(type_name, fields, location)
    literal = StructLiteral(
        type_name,
        tuple(
            (f"c{index}", _base._lower_value(value, location))
            for index, value in enumerate(cells)
        ),
        location,
    )
    origin = GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=TypeRef((type_name,), location),
        body=Block((ReturnStatement(literal, location),)),
        location=location,
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    program = Program((origin,), structs=(declaration,))
    semantic = SemanticChecker(program).check()
    return program, semantic


def is_native_cell_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(CELL_GRAPH_MAGIC_V1)


def encode_native_cell_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    schema_id: bytes,
    cell_witnesses: Sequence[str],
) -> bytes:
    project = _exact(project_id, _ID_BYTES, "project id")
    root = _exact(root_object_id, _ID_BYTES, "root object id")
    schema = _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    if not isinstance(objects, Mapping) or set(objects) != {root}:
        _fail("native cell reality v1 requires exactly one authoritative root object")
    if (
        not isinstance(cell_witnesses, Sequence)
        or isinstance(cell_witnesses, (str, bytes))
        or not 1 <= len(cell_witnesses) <= MAX_CELL_COUNT_V1
    ):
        _fail(f"cell_witnesses must contain 1..{MAX_CELL_COUNT_V1} entries")
    names = tuple(cell_witnesses)
    if len(set(names)) != len(names) or any(not isinstance(name, str) for name in names):
        _fail("cell_witnesses must be unique text witness identities")

    source_bytes = objects[root]
    source = _parse_cell_source(_source(source_bytes))
    if set(source.resolves) != set(names):
        _fail("source resolve set must exactly match sealed cell witness set")
    order, values = _evaluate_cell_source(source, names)
    del order
    digest = hashlib.sha256(source_bytes).digest()

    records: list[NativeCellRecordV1] = []
    seen_tags: set[bytes] = set()
    for ordinal, name in enumerate(names):
        value = values.get(name)
        if value is None:
            _fail(f"sealed cell witness {name!r} is unresolved")
        tag = _witness_tag(
            project_id=project,
            root_object_id=root,
            source_digest=digest,
            witness_name=name,
        )
        if tag in seen_tags:
            _fail("cell witness tag collision")
        seen_tags.add(tag)
        records.append(NativeCellRecordV1(ordinal, tag, value.domain))

    body = bytearray(
        _HEADER.pack(
            CELL_GRAPH_MAGIC_V1,
            CELL_GRAPH_VERSION_V1,
            project,
            root,
            digest,
            NATIVE_CELL_FRONTEND_V1,
            schema,
            len(records),
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
        _fail("native cell graph exceeds sealed graph byte budget")
    return bytes(body)


def decode_native_cell_graph(project: ObjectSpaceProject) -> NativeCellRealityCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native cell graph requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size:
        _fail("native cell graph is truncated")
    (
        magic,
        version,
        project_id,
        root_id,
        digest,
        frontend,
        schema_id,
        cell_count,
    ) = _HEADER.unpack_from(payload, 0)
    if magic != CELL_GRAPH_MAGIC_V1 or version != CELL_GRAPH_VERSION_V1:
        _fail("native cell graph schema is invalid")
    if project_id != project.project_id or root_id != project.root_object_id:
        _fail("native cell graph trusted project/root context mismatch")
    if frontend != NATIVE_CELL_FRONTEND_V1:
        _fail("native cell frontend identity mismatch")
    _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    if not 1 <= cell_count <= MAX_CELL_COUNT_V1:
        _fail("native cell count is outside policy")
    expected_size = _HEADER.size + cell_count * _CELL.size
    if len(payload) != expected_size:
        _fail("native cell graph count/length relation is non-canonical")
    if len(project.records) != 1 or project.records[0].object_id != root_id:
        _fail("native cell object set differs from sealed k0 authority")
    if set(project.object_payloads) != {root_id}:
        _fail("opened native cell payload set differs from authority")
    if project.records[0].artifact_digest != digest:
        _fail("native cell source digest differs from sealed k0 authority")
    source_bytes = project.object_payloads[root_id]
    if hashlib.sha256(source_bytes).digest() != digest:
        _fail("opened native cell source digest differs from authenticated authority")

    records: list[NativeCellRecordV1] = []
    offset = _HEADER.size
    for expected_ordinal in range(cell_count):
        ordinal, tag, domain_code = _CELL.unpack_from(payload, offset)
        offset += _CELL.size
        if ordinal != expected_ordinal:
            _fail("native cell table is not canonical ordinal order")
        domain = _CODE_TO_DOMAIN.get(domain_code)
        if domain is None:
            _fail("native cell domain code is invalid")
        records.append(NativeCellRecordV1(ordinal, tag, domain))

    source = _parse_cell_source(_source(source_bytes))
    by_tag: dict[bytes, str] = {}
    for name in source.resolves:
        tag = _witness_tag(
            project_id=project.project_id,
            root_object_id=root_id,
            source_digest=digest,
            witness_name=name,
        )
        if tag in by_tag:
            _fail("native cell witness tag collision during load")
        by_tag[tag] = name

    ordered_names: list[str] = []
    for record in records:
        name = by_tag.get(record.witness_tag)
        if name is None:
            _fail("sealed cell record does not match any resolved source witness")
        ordered_names.append(name)
    if set(ordered_names) != set(source.resolves) or len(ordered_names) != len(source.resolves):
        _fail("sealed cell table does not exactly cover source resolve set")

    order, values = _evaluate_cell_source(source, ordered_names)
    cells: list[_base.NativeValue] = []
    for record, name in zip(records, ordered_names):
        value = values[name]
        if value.domain != record.domain:
            _fail("sealed cell domain contract differs from evaluated source reality")
        cells.append(value)

    lowered, semantic = _lower_cell_reality(cells)
    return NativeCellRealityCheckV1(
        source=source,
        schema_id=schema_id,
        ordered_witnesses=tuple(ordered_names),
        dependency_order=order,
        values=values,
        cells=tuple(cells),
        lowered=lowered,
        semantic=semantic,
    )


def check_native_cell_object_space(project: ObjectSpaceProject):
    checked = decode_native_cell_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-cell-root>",
                path=Path("<koschei-native-cell-root>"),
                program=checked.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
