"""Sealed mixed-domain Native Cell -> reusable composition v1.

This slice extends the #204 composition path without changing its Whole-only v1
contract. A distinct authenticated graph/frontend admits ``whole``, ``truth`` and
``glyphs`` cell values into one reusable conduit reality and seals the reusable
result domain before the root consumes it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import struct
from typing import Mapping, Sequence

from .modules import Module, ModuleGraph, check_graph
from .native_cell_realities_v1 import (
    MAX_CELL_COUNT_V1,
    NATIVE_CELL_FRONTEND_V1,
    NativeCellRecordV1,
    NativeCellRealityError,
    _CELL,
    _CODE_TO_DOMAIN,
    _DOMAIN_TO_CODE,
    _evaluate_cell_source,
    _parse_cell_source,
    _witness_tag,
)
from .native_cell_reuse_composition_v1 import _cell_names, _cell_source
from .native_kernel_v1 import MAX_WITNESSES
from .native_relationship_v1 import MAX_ABS_INT64, MAX_RELATION_SLOT_V1, _positive_epoch, _u64
from .native_reusable_realities_v1 import MAX_REALIZATION_INPUTS_V1
from .native_value_domains_v1 import (
    GLYPHS,
    TRUTH,
    WHOLE,
    NativeValue,
    NativeValueDomainCheck,
    ValueAtom,
    ValueTerm,
    _canonical_lines,
    dependency_order_value_graph,
    evaluate_native_value_graph,
    lower_native_value_graph,
    parse_native_value_graph,
)
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, ObjectSpaceError, ObjectSpaceProject
from .semantic import SemanticChecker


MIXED_REUSE_GRAPH_MAGIC_V1 = b"KOSCHEI_MIXREU1\x00"
MIXED_REUSE_GRAPH_VERSION_V1 = 1
_ROOT_CONTEXT = b"koschei.frontend/native-mixed-reuse-root/v1"
_REUSABLE_CONTEXT = b"koschei.frontend/native-mixed-reusable-reality/v1"
NATIVE_MIXED_REUSE_FRONTEND_V1 = hashlib.sha256(_ROOT_CONTEXT).digest()
NATIVE_MIXED_REUSABLE_OBJECT_FRONTEND_V1 = hashlib.sha256(_REUSABLE_CONTEXT).digest()

_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32
_SCHEMA_ID_BYTES = 16
_OBJECT_COUNT_V1 = 3

# magic/version/project/root/cell/reusable/schema, counts, root slot, realization,
# epochs, witness ceiling, whole input/output ceilings, authority/effect ceilings,
# glyph input/output byte ceilings, sealed reusable output-domain code.
_HEADER = struct.Struct(
    ">16sB7x16s16s16s16s16sHHI16sQQI4xQQQQIIB7x"
)
_OBJECT = struct.Struct(">16s32s32s")
_BINDING = struct.Struct(">HHB3x")


class NativeMixedReuseError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeMixedReuseCheckV1:
    schema_id: bytes
    ordered_cell_witnesses: tuple[str, ...]
    cell_values: tuple[NativeValue, ...]
    input_cell_ordinals: tuple[int, ...]
    input_domains: tuple[str, ...]
    reusable: NativeValueDomainCheck
    root: NativeValueDomainCheck


def _fail(message: str) -> None:
    raise NativeMixedReuseError(message)


def _exact(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _decode_utf8(payload: bytes, label: str) -> str:
    if not isinstance(payload, bytes):
        _fail(f"{label} payload must be bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NativeMixedReuseError(f"{label} payload is not valid UTF-8") from error


def _conduit_contract(source: str) -> tuple[tuple[int, str], ...]:
    lines = _canonical_lines(source)
    found: list[tuple[int, str]] = []
    slots: set[int] = set()
    for line in lines:
        tokens = line.split(" ")
        if "conduit" not in tokens:
            continue
        if len(tokens) != 4 or tokens[0] != "witness" or tokens[2] != "conduit":
            _fail("'conduit' is valid only as: witness <name> conduit <slot>")
        raw = tokens[3]
        if not raw.isascii() or not raw.isdigit() or (len(raw) > 1 and raw.startswith("0")):
            _fail("mixed reusable conduit slot is not canonical unsigned decimal")
        if len(raw) > 5:
            _fail("mixed reusable conduit slot exceeds v1 range")
        slot = int(raw)
        if slot > MAX_RELATION_SLOT_V1 or slot in slots:
            _fail("mixed reusable conduit slot is duplicate or outside v1 range")
        slots.add(slot)
        found.append((slot, tokens[1]))
    found.sort(key=lambda item: item[0])
    if not found:
        _fail("mixed reusable reality must expose at least one conduit input")
    if len(found) > MAX_REALIZATION_INPUTS_V1:
        _fail("mixed reusable reality exposes too many conduit inputs")
    if tuple(slot for slot, _ in found) != tuple(range(len(found))):
        _fail("mixed reusable conduit inputs must be contiguous from slot 0")
    return tuple(found)


def _materialize_typed(source: str, values_by_slot: Mapping[int, NativeValue]) -> NativeValueDomainCheck:
    lines = list(_canonical_lines(source))
    conduits = _conduit_contract(source)
    if {slot for slot, _ in conduits} != set(values_by_slot):
        _fail("typed conduit slots do not exactly match sealed bindings")
    witness_by_slot = {slot: name for slot, name in conduits}
    replaced_lines: list[str] = []
    for line in lines:
        tokens = line.split(" ")
        if len(tokens) == 4 and tokens[0] == "witness" and tokens[2] == "conduit":
            replaced_lines.append(f"witness {tokens[1]} 0")
        else:
            if "conduit" in tokens:
                _fail("'conduit' is valid only as a witness input aperture")
            replaced_lines.append(line)
    try:
        graph = parse_native_value_graph("\n".join(replaced_lines) + "\n")
    except Exception as error:
        raise NativeMixedReuseError(str(error)) from error
    replacement_by_name = {witness_by_slot[slot]: value for slot, value in values_by_slot.items()}
    witnesses = []
    for witness in graph.witnesses:
        value = replacement_by_name.get(witness.name)
        if value is None:
            witnesses.append(witness)
        else:
            witnesses.append(
                replace(witness, term=ValueTerm(None, (ValueAtom(literal=value),)))
            )
    graph = replace(graph, witnesses=tuple(witnesses))
    try:
        order = dependency_order_value_graph(graph)
        values = evaluate_native_value_graph(graph)
        lowered = lower_native_value_graph(graph, values)
        semantic = SemanticChecker(lowered).check()
    except Exception as error:
        raise NativeMixedReuseError(str(error)) from error
    return NativeValueDomainCheck(graph, order, values, values[graph.resolve], lowered, semantic)


def _validate_value_budget(
    value: NativeValue,
    *,
    max_abs_whole: int,
    max_glyph_bytes: int,
    label: str,
) -> None:
    if value.domain == WHOLE:
        if abs(int(value.value)) > max_abs_whole:
            _fail(f"{label} whole value exceeds sealed absolute-value ceiling")
        return
    if value.domain == TRUTH:
        return
    if value.domain == GLYPHS:
        if len(str(value.value).encode("utf-8")) > max_glyph_bytes:
            _fail(f"{label} glyphs value exceeds sealed byte ceiling")
        return
    _fail(f"{label} uses unsupported scalar domain")


def _object_records(*, root_id: bytes, cell_id: bytes, reusable_id: bytes, objects: Mapping[bytes, bytes]):
    if not isinstance(objects, Mapping) or set(objects) != {root_id, cell_id, reusable_id}:
        _fail("mixed reuse v1 requires exactly root, cell and reusable authoritative objects")
    frontends = {
        root_id: NATIVE_MIXED_REUSE_FRONTEND_V1,
        cell_id: NATIVE_CELL_FRONTEND_V1,
        reusable_id: NATIVE_MIXED_REUSABLE_OBJECT_FRONTEND_V1,
    }
    return tuple(
        (object_id, hashlib.sha256(objects[object_id]).digest(), frontends[object_id])
        for object_id in sorted(objects)
    )


def is_native_mixed_reuse_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(MIXED_REUSE_GRAPH_MAGIC_V1)


def encode_native_mixed_reuse_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    cell_object_id: bytes,
    reusable_object_id: bytes,
    objects: Mapping[bytes, bytes],
    schema_id: bytes,
    cell_witnesses: Sequence[str],
    input_cell_ordinals: Sequence[int],
    root_slot: int,
    realization_id: bytes,
    expected_output_domain: str,
    current_epoch: int,
    issued_epoch: int,
    expires_epoch: int,
    max_reusable_witnesses: int = MAX_WITNESSES,
    max_abs_input: int = MAX_ABS_INT64,
    max_abs_output: int = MAX_ABS_INT64,
    max_glyph_input_bytes: int = 1 << 20,
    max_glyph_output_bytes: int = 1 << 20,
    authority_ceiling: int = 0,
    effect_ceiling: int = 0,
) -> bytes:
    project = _exact(project_id, _ID_BYTES, "project id")
    root = _exact(root_object_id, _ID_BYTES, "root object id")
    cell_id = _exact(cell_object_id, _ID_BYTES, "cell object id")
    reusable_id = _exact(reusable_object_id, _ID_BYTES, "reusable object id")
    if len({root, cell_id, reusable_id}) != 3:
        _fail("mixed reuse object identities must be distinct")
    schema = _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    realization = _exact(realization_id, _ID_BYTES, "realization id")
    epoch = _positive_epoch(current_epoch, "current Object Space epoch")
    issued = _positive_epoch(issued_epoch, "mixed reuse issued epoch")
    expires = _positive_epoch(expires_epoch, "mixed reuse expiry epoch")
    if issued > epoch or epoch > expires:
        _fail("mixed reuse graph is stale or not yet valid")
    authority = _u64(authority_ceiling, "mixed reuse authority ceiling")
    effects = _u64(effect_ceiling, "mixed reuse effect ceiling")
    if authority or effects:
        _fail("mixed reuse v1 admits only zero authority and zero effects")
    if expected_output_domain not in _DOMAIN_TO_CODE:
        _fail("mixed reuse expected output domain is invalid")
    if not 1 <= max_reusable_witnesses <= MAX_WITNESSES:
        _fail("mixed reusable witness ceiling is outside v1 bounds")
    max_input = _u64(max_abs_input, "mixed reuse whole input ceiling")
    max_output = _u64(max_abs_output, "mixed reuse whole output ceiling")
    glyph_input = _u64(max_glyph_input_bytes, "mixed reuse glyph input ceiling")
    glyph_output = _u64(max_glyph_output_bytes, "mixed reuse glyph output ceiling")
    if max_input > MAX_ABS_INT64 or max_output > MAX_ABS_INT64:
        _fail("mixed reuse whole ceiling exceeds signed Int64 reality")
    if glyph_input > (1 << 20) or glyph_output > (1 << 20):
        _fail("mixed reuse glyph ceiling exceeds native value-domain v1 budget")

    records = _object_records(root_id=root, cell_id=cell_id, reusable_id=reusable_id, objects=objects)
    names = _cell_names(cell_witnesses)
    cell_bytes = objects[cell_id]
    cell_digest = hashlib.sha256(cell_bytes).digest()
    try:
        parsed = _parse_cell_source(_cell_source(cell_bytes))
        if set(parsed.resolves) != set(names):
            _fail("mixed reuse source resolve set must exactly match sealed cell set")
        _, values_by_name = _evaluate_cell_source(parsed, names)
    except NativeCellRealityError as error:
        raise NativeMixedReuseError(str(error)) from error
    cell_records = tuple(
        NativeCellRecordV1(
            ordinal,
            _witness_tag(
                project_id=project,
                root_object_id=cell_id,
                source_digest=cell_digest,
                witness_name=name,
            ),
            values_by_name[name].domain,
        )
        for ordinal, name in enumerate(names)
    )
    reusable_source = _decode_utf8(objects[reusable_id], "mixed reusable reality")
    conduits = _conduit_contract(reusable_source)
    if not isinstance(input_cell_ordinals, Sequence) or isinstance(input_cell_ordinals, (str, bytes)):
        _fail("mixed reuse input bindings must be an ordered sequence")
    if len(input_cell_ordinals) != len(conduits):
        _fail("mixed reuse binding count must exactly match reusable conduit contract")
    bindings: list[int] = []
    inputs: dict[int, NativeValue] = {}
    for (slot, _), raw in zip(conduits, input_cell_ordinals):
        if not isinstance(raw, int) or isinstance(raw, bool) or not 0 <= raw < len(cell_records):
            _fail("mixed reuse input binding references cell outside sealed schema")
        value = values_by_name[names[raw]]
        _validate_value_budget(value, max_abs_whole=max_input, max_glyph_bytes=glyph_input, label="mixed reuse input")
        bindings.append(raw)
        inputs[slot] = value
    reusable_check = _materialize_typed(reusable_source, inputs)
    if len(reusable_check.graph.witnesses) > max_reusable_witnesses:
        _fail("mixed reusable reality exceeds sealed witness ceiling")
    if reusable_check.value.domain != expected_output_domain:
        _fail("mixed reusable result domain differs from sealed output domain")
    _validate_value_budget(reusable_check.value, max_abs_whole=max_output, max_glyph_bytes=glyph_output, label="mixed reuse output")

    root_source = _decode_utf8(objects[root], "mixed reuse root")
    root_conduits = _conduit_contract(root_source)
    if tuple(slot for slot, _ in root_conduits) != (root_slot,):
        _fail("mixed reuse root must expose exactly the sealed reusable result slot")
    _materialize_typed(root_source, {root_slot: reusable_check.value})

    body = bytearray(
        _HEADER.pack(
            MIXED_REUSE_GRAPH_MAGIC_V1,
            MIXED_REUSE_GRAPH_VERSION_V1,
            project,
            root,
            cell_id,
            reusable_id,
            schema,
            len(cell_records),
            len(bindings),
            root_slot,
            realization,
            issued,
            expires,
            max_reusable_witnesses,
            max_input,
            max_output,
            authority,
            effects,
            glyph_input,
            glyph_output,
            _DOMAIN_TO_CODE[expected_output_domain],
        )
    )
    for item in records:
        body.extend(_OBJECT.pack(*item))
    for record in cell_records:
        body.extend(_CELL.pack(record.ordinal, record.witness_tag, _DOMAIN_TO_CODE[record.domain]))
    for input_slot, ordinal in enumerate(bindings):
        body.extend(_BINDING.pack(input_slot, ordinal, _DOMAIN_TO_CODE[cell_records[ordinal].domain]))
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("mixed reuse graph exceeds sealed graph byte budget")
    return bytes(body)


def decode_native_mixed_reuse_graph(project: ObjectSpaceProject) -> NativeMixedReuseCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("mixed reuse requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size + _OBJECT_COUNT_V1 * _OBJECT.size:
        _fail("mixed reuse graph is truncated")
    unpacked = _HEADER.unpack_from(payload, 0)
    (
        magic, version, project_id, root_id, cell_id, reusable_id, schema_id,
        cell_count, input_count, root_slot, realization_id, issued, expires,
        witness_ceiling, max_input, max_output, authority, effects,
        glyph_input, glyph_output, output_domain_code,
    ) = unpacked
    if magic != MIXED_REUSE_GRAPH_MAGIC_V1 or version != MIXED_REUSE_GRAPH_VERSION_V1:
        _fail("mixed reuse graph schema is invalid")
    if project_id != project.project_id or root_id != project.root_object_id:
        _fail("mixed reuse trusted project/root context mismatch")
    _exact(cell_id, _ID_BYTES, "cell object id")
    _exact(reusable_id, _ID_BYTES, "reusable object id")
    _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    _exact(realization_id, _ID_BYTES, "realization id")
    if len({root_id, cell_id, reusable_id}) != 3:
        _fail("mixed reuse object roles must use distinct identities")
    if not 1 <= cell_count <= MAX_CELL_COUNT_V1 or not 1 <= input_count <= MAX_REALIZATION_INPUTS_V1:
        _fail("mixed reuse counts are outside v1 policy")
    if not 0 <= root_slot <= MAX_RELATION_SLOT_V1:
        _fail("mixed reuse root slot is outside v1 policy")
    if not 1 <= issued <= project.epoch <= expires <= (1 << 64) - 1:
        _fail("mixed reuse graph is stale or not yet valid")
    if authority or effects:
        _fail("mixed reuse graph rejects authority/effect inflation")
    if not 1 <= witness_ceiling <= MAX_WITNESSES:
        _fail("mixed reusable witness ceiling is outside v1 policy")
    if max_input > MAX_ABS_INT64 or max_output > MAX_ABS_INT64 or glyph_input > (1 << 20) or glyph_output > (1 << 20):
        _fail("mixed reuse value budget is outside native v1 policy")
    output_domain = _CODE_TO_DOMAIN.get(output_domain_code)
    if output_domain is None:
        _fail("mixed reuse sealed output domain code is invalid")

    expected_size = _HEADER.size + _OBJECT_COUNT_V1 * _OBJECT.size + cell_count * _CELL.size + input_count * _BINDING.size
    if len(payload) != expected_size:
        _fail("mixed reuse graph count/length relation is non-canonical")

    offset = _HEADER.size
    frontends = {
        root_id: NATIVE_MIXED_REUSE_FRONTEND_V1,
        cell_id: NATIVE_CELL_FRONTEND_V1,
        reusable_id: NATIVE_MIXED_REUSABLE_OBJECT_FRONTEND_V1,
    }
    records = []
    seen = set()
    for _ in range(_OBJECT_COUNT_V1):
        object_id, digest, frontend = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        if object_id in seen or object_id not in frontends or frontend != frontends[object_id]:
            _fail("mixed reuse object table contains duplicate/unknown role or frontend mismatch")
        seen.add(object_id)
        records.append((object_id, digest, frontend))
    if records != sorted(records, key=lambda item: item[0]) or seen != {root_id, cell_id, reusable_id}:
        _fail("mixed reuse object table is non-canonical")
    k0 = {record.object_id: record for record in project.records}
    if set(k0) != seen or set(project.object_payloads) != seen:
        _fail("mixed reuse object set differs from sealed k0 authority")
    digest_by_id = {}
    for object_id, digest, _ in records:
        if k0[object_id].artifact_digest != digest or hashlib.sha256(project.object_payloads[object_id]).digest() != digest:
            _fail("mixed reuse object digest differs from authenticated authority")
        digest_by_id[object_id] = digest

    cell_records = []
    for expected_ordinal in range(cell_count):
        ordinal, tag, domain_code = _CELL.unpack_from(payload, offset)
        offset += _CELL.size
        domain = _CODE_TO_DOMAIN.get(domain_code)
        if ordinal != expected_ordinal or domain is None:
            _fail("mixed reuse cell table is non-canonical")
        cell_records.append(NativeCellRecordV1(ordinal, tag, domain))

    bindings = []
    binding_domains = []
    for expected_input in range(input_count):
        input_slot, ordinal, domain_code = _BINDING.unpack_from(payload, offset)
        offset += _BINDING.size
        domain = _CODE_TO_DOMAIN.get(domain_code)
        if input_slot != expected_input or ordinal >= cell_count or domain is None:
            _fail("mixed reuse binding table is non-canonical")
        if domain != cell_records[ordinal].domain:
            _fail("mixed reuse binding domain differs from sealed cell domain")
        bindings.append(ordinal)
        binding_domains.append(domain)

    cell_bytes = project.object_payloads[cell_id]
    try:
        parsed = _parse_cell_source(_cell_source(cell_bytes))
    except NativeCellRealityError as error:
        raise NativeMixedReuseError(str(error)) from error
    by_tag = {}
    for name in parsed.resolves:
        tag = _witness_tag(
            project_id=project.project_id,
            root_object_id=cell_id,
            source_digest=digest_by_id[cell_id],
            witness_name=name,
        )
        if tag in by_tag:
            _fail("mixed reuse cell witness tag collision")
        by_tag[tag] = name
    ordered_names = []
    for record in cell_records:
        name = by_tag.get(record.witness_tag)
        if name is None:
            _fail("mixed reuse sealed cell does not match resolved source witness")
        ordered_names.append(name)
    if set(ordered_names) != set(parsed.resolves) or len(ordered_names) != len(parsed.resolves):
        _fail("mixed reuse cell table does not exactly cover source resolve set")
    try:
        _, values_by_name = _evaluate_cell_source(parsed, ordered_names)
    except NativeCellRealityError as error:
        raise NativeMixedReuseError(str(error)) from error
    cell_values = tuple(values_by_name[name] for name in ordered_names)
    for record, value in zip(cell_records, cell_values):
        if record.domain != value.domain:
            _fail("mixed reuse full cell schema domain differs from evaluated source")

    reusable_source = _decode_utf8(project.object_payloads[reusable_id], "mixed reusable reality")
    conduits = _conduit_contract(reusable_source)
    if len(conduits) != input_count:
        _fail("mixed reuse input count differs from reusable conduit contract")
    inputs = {}
    for slot, ordinal in enumerate(bindings):
        value = cell_values[ordinal]
        if value.domain != binding_domains[slot]:
            _fail("mixed reuse projected input domain differs from sealed binding")
        _validate_value_budget(value, max_abs_whole=max_input, max_glyph_bytes=glyph_input, label="mixed reuse input")
        inputs[slot] = value
    reusable_check = _materialize_typed(reusable_source, inputs)
    if len(reusable_check.graph.witnesses) > witness_ceiling:
        _fail("mixed reusable reality exceeds sealed witness ceiling")
    if reusable_check.value.domain != output_domain:
        _fail("mixed reusable result domain differs from sealed output domain")
    _validate_value_budget(reusable_check.value, max_abs_whole=max_output, max_glyph_bytes=glyph_output, label="mixed reuse output")

    root_source = _decode_utf8(project.object_payloads[root_id], "mixed reuse root")
    root_conduits = _conduit_contract(root_source)
    if tuple(slot for slot, _ in root_conduits) != (root_slot,):
        _fail("mixed reuse root must expose exactly the sealed result slot")
    root_check = _materialize_typed(root_source, {root_slot: reusable_check.value})
    return NativeMixedReuseCheckV1(
        schema_id=schema_id,
        ordered_cell_witnesses=tuple(ordered_names),
        cell_values=cell_values,
        input_cell_ordinals=tuple(bindings),
        input_domains=tuple(binding_domains),
        reusable=reusable_check,
        root=root_check,
    )


def check_native_mixed_reuse_object_space(project: ObjectSpaceProject):
    checked = decode_native_mixed_reuse_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-mixed-reuse-root>",
                path=Path("<koschei-native-mixed-reuse-root>"),
                program=checked.root.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
