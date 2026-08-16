"""Authenticated Native Cell -> Reusable composition v1.

This slice proves an end-to-end data/model path without source-level member access
or function calls:

    full sealed cell reality
      -> schema-bound whole-cell input bindings
      -> one reusable conduit reality
      -> one root conduit reality

All three source objects are authoritative Object Space objects. The complete cell
schema is validated before any selected cell becomes a reusable input. V1 is pure
and Whole-input/output only at the reuse boundary; unselected cells may be other
native scalar domains and are still fully validated.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    _DOMAIN_TO_CODE,
    _CODE_TO_DOMAIN,
    _evaluate_cell_source,
    _parse_cell_source,
    _witness_tag,
)
from .native_reusable_realities_v1 import (
    MAX_REALIZATION_INPUTS_V1,
    NATIVE_REUSABLE_OBJECT_FRONTEND_V1,
    _template_contract,
    _validate_input,
)
from .native_relationship_v1 import (
    MAX_ABS_INT64,
    MAX_RELATION_SLOT_V1,
    _conduit_slots,
    _decode_ascii,
    _exact_bytes,
    _materialize_root,
    _positive_epoch,
    _u64,
)
from .native_kernel_v1 import MAX_WITNESSES, NativeKernelCheck
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, ObjectSpaceError, ObjectSpaceProject


COMPOSITION_GRAPH_MAGIC_V1 = b"KOSCHEI_OSCOMP1\x00"
COMPOSITION_GRAPH_VERSION_V1 = 1
_COMPOSITION_FRONTEND_CONTEXT = b"koschei.frontend/native-cell-reuse-composition/v1"
NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1 = hashlib.sha256(
    _COMPOSITION_FRONTEND_CONTEXT
).digest()

_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32
_SCHEMA_ID_BYTES = 16
_OBJECT_COUNT_V1 = 3

# magic/version/project/root/cell/reusable ids, schema id, cell count/input count,
# root slot, realization id, issued/expiry, witness ceiling, abs input/output,
# authority/effects
_HEADER = struct.Struct(
    ">16sB7x16s16s16s16s16sHHI16sQQI4xQQQQ"
)
_OBJECT = struct.Struct(">16s32s32s")
# reusable input slot -> full-schema cell ordinal; domain is repeated fail-closed.
_BINDING = struct.Struct(">HHB3x")


class NativeCellReuseCompositionError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCellReuseCompositionCheckV1:
    schema_id: bytes
    ordered_cell_witnesses: tuple[str, ...]
    cell_values: tuple[object, ...]
    input_cell_ordinals: tuple[int, ...]
    reusable: NativeKernelCheck
    root: NativeKernelCheck


def _fail(message: str) -> None:
    raise NativeCellReuseCompositionError(message)


def _exact(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _cell_source(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        _fail("composition cell source must be bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NativeCellReuseCompositionError(
            "composition cell source is not valid UTF-8"
        ) from error


def _cell_names(cell_witnesses: Sequence[str]) -> tuple[str, ...]:
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


def _object_records(
    *,
    root_id: bytes,
    cell_id: bytes,
    reusable_id: bytes,
    objects: Mapping[bytes, bytes],
) -> tuple[tuple[bytes, bytes, bytes], ...]:
    if not isinstance(objects, Mapping) or set(objects) != {root_id, cell_id, reusable_id}:
        _fail("composition v1 requires exactly root, cell and reusable authoritative objects")
    expected_frontends = {
        root_id: NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1,
        cell_id: NATIVE_CELL_FRONTEND_V1,
        reusable_id: NATIVE_REUSABLE_OBJECT_FRONTEND_V1,
    }
    records = [
        (object_id, hashlib.sha256(objects[object_id]).digest(), expected_frontends[object_id])
        for object_id in sorted(objects)
    ]
    return tuple(records)


def _validate_root_contract(root_source: str, root_slot: int) -> None:
    if not isinstance(root_slot, int) or isinstance(root_slot, bool) or not 0 <= root_slot <= MAX_RELATION_SLOT_V1:
        _fail("composition root slot is outside v1 range")
    slots = {slot for slot, _, _ in _conduit_slots(root_source)}
    if slots != {root_slot}:
        _fail("composition root must expose exactly the sealed reusable result slot")


def _validate_bindings(
    *,
    reusable_source: str,
    input_cell_ordinals: Sequence[int],
    cell_domains: Sequence[str],
) -> tuple[int, ...]:
    slots = _template_contract(reusable_source)
    if (
        not isinstance(input_cell_ordinals, Sequence)
        or isinstance(input_cell_ordinals, (str, bytes))
        or len(input_cell_ordinals) != len(slots)
    ):
        _fail("composition input binding count must exactly match reusable conduit contract")
    if len(slots) > MAX_REALIZATION_INPUTS_V1:
        _fail("composition reusable input count exceeds v1 policy")
    ordinals: list[int] = []
    for slot, raw in zip(slots, input_cell_ordinals):
        if not isinstance(raw, int) or isinstance(raw, bool) or not 0 <= raw < len(cell_domains):
            _fail("composition input binding references a cell ordinal outside the sealed schema")
        if cell_domains[raw] != "whole":
            _fail(
                f"composition reusable input slot {slot} requires whole cell domain in v1"
            )
        ordinals.append(raw)
    return tuple(ordinals)


def is_native_cell_reuse_composition_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(COMPOSITION_GRAPH_MAGIC_V1)


def encode_native_cell_reuse_composition_graph_secret(
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
    current_epoch: int,
    issued_epoch: int,
    expires_epoch: int,
    max_reusable_witnesses: int = MAX_WITNESSES,
    max_abs_input: int = MAX_ABS_INT64,
    max_abs_output: int = MAX_ABS_INT64,
    authority_ceiling: int = 0,
    effect_ceiling: int = 0,
) -> bytes:
    project = _exact(project_id, _ID_BYTES, "project id")
    root = _exact(root_object_id, _ID_BYTES, "root object id")
    cell_id = _exact(cell_object_id, _ID_BYTES, "cell object id")
    reusable_id = _exact(reusable_object_id, _ID_BYTES, "reusable object id")
    if len({root, cell_id, reusable_id}) != 3:
        _fail("composition root, cell and reusable identities must be distinct")
    schema = _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    realization = _exact(realization_id, _ID_BYTES, "realization id")
    epoch = _positive_epoch(current_epoch, "current Object Space epoch")
    issued = _positive_epoch(issued_epoch, "composition issued epoch")
    expires = _positive_epoch(expires_epoch, "composition expiry epoch")
    if issued > epoch or epoch > expires:
        _fail("composition is stale or not yet valid for this Object Space epoch")
    authority = _u64(authority_ceiling, "composition authority ceiling")
    effects = _u64(effect_ceiling, "composition effect ceiling")
    if authority != 0 or effects != 0:
        _fail("native cell/reuse composition v1 admits only zero authority and zero effects")
    if (
        not isinstance(max_reusable_witnesses, int)
        or isinstance(max_reusable_witnesses, bool)
        or not 1 <= max_reusable_witnesses <= MAX_WITNESSES
    ):
        _fail("composition reusable witness ceiling is outside native v1 bounds")
    max_input = _u64(max_abs_input, "composition absolute input ceiling")
    max_output = _u64(max_abs_output, "composition absolute output ceiling")
    if max_input > MAX_ABS_INT64 or max_output > MAX_ABS_INT64:
        _fail("composition absolute ceiling exceeds signed Int64 reality")

    records = _object_records(
        root_id=root,
        cell_id=cell_id,
        reusable_id=reusable_id,
        objects=objects,
    )
    names = _cell_names(cell_witnesses)
    cell_bytes = objects[cell_id]
    cell_digest = hashlib.sha256(cell_bytes).digest()
    try:
        parsed = _parse_cell_source(_cell_source(cell_bytes))
        if set(parsed.resolves) != set(names):
            _fail("composition source resolve set must exactly match sealed cell set")
        _, values = _evaluate_cell_source(parsed, names)
    except NativeCellRealityError as error:
        raise NativeCellReuseCompositionError(str(error)) from error

    cell_records: list[NativeCellRecordV1] = []
    for ordinal, name in enumerate(names):
        value = values[name]
        cell_records.append(
            NativeCellRecordV1(
                ordinal,
                _witness_tag(
                    project_id=project,
                    root_object_id=cell_id,
                    source_digest=cell_digest,
                    witness_name=name,
                ),
                value.domain,
            )
        )
    reusable_source = _decode_ascii(objects[reusable_id], "composition reusable reality")
    ordinals = _validate_bindings(
        reusable_source=reusable_source,
        input_cell_ordinals=input_cell_ordinals,
        cell_domains=[record.domain for record in cell_records],
    )
    inputs = tuple(
        _validate_input(int(values[names[ordinal]].value), max_abs_input=max_input)
        for ordinal in ordinals
    )
    reusable_slots = _template_contract(reusable_source)
    reusable_check = _materialize_root(
        reusable_source,
        {slot: inputs[index] for index, slot in enumerate(reusable_slots)},
    )
    if len(reusable_check.kernel.witnesses) > max_reusable_witnesses:
        _fail("composition reusable reality exceeds sealed witness ceiling")
    if abs(reusable_check.value) > max_output:
        _fail("composition reusable output exceeds sealed absolute-value ceiling")

    root_source = _decode_ascii(objects[root], "composition root")
    _validate_root_contract(root_source, root_slot)
    _materialize_root(root_source, {root_slot: reusable_check.value})

    body = bytearray(
        _HEADER.pack(
            COMPOSITION_GRAPH_MAGIC_V1,
            COMPOSITION_GRAPH_VERSION_V1,
            project,
            root,
            cell_id,
            reusable_id,
            schema,
            len(cell_records),
            len(ordinals),
            root_slot,
            realization,
            issued,
            expires,
            max_reusable_witnesses,
            max_input,
            max_output,
            authority,
            effects,
        )
    )
    for item in records:
        body.extend(_OBJECT.pack(*item))
    for record in cell_records:
        body.extend(_CELL.pack(record.ordinal, record.witness_tag, _DOMAIN_TO_CODE[record.domain]))
    for input_slot, ordinal in enumerate(ordinals):
        body.extend(_BINDING.pack(input_slot, ordinal, _DOMAIN_TO_CODE["whole"]))
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("native cell/reuse composition exceeds sealed graph byte budget")
    return bytes(body)


def decode_native_cell_reuse_composition_graph(
    project: ObjectSpaceProject,
) -> NativeCellReuseCompositionCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native cell/reuse composition requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size + _OBJECT_COUNT_V1 * _OBJECT.size:
        _fail("native cell/reuse composition graph is truncated")
    (
        magic,
        version,
        project_id,
        root_id,
        cell_id,
        reusable_id,
        schema_id,
        cell_count,
        input_count,
        root_slot,
        realization_id,
        issued,
        expires,
        witness_ceiling,
        max_input,
        max_output,
        authority,
        effects,
    ) = _HEADER.unpack_from(payload, 0)
    if magic != COMPOSITION_GRAPH_MAGIC_V1 or version != COMPOSITION_GRAPH_VERSION_V1:
        _fail("native cell/reuse composition schema is invalid")
    if project_id != project.project_id or root_id != project.root_object_id:
        _fail("composition trusted project/root context mismatch")
    _exact(cell_id, _ID_BYTES, "cell object id")
    _exact(reusable_id, _ID_BYTES, "reusable object id")
    _exact(schema_id, _SCHEMA_ID_BYTES, "cell schema id")
    _exact(realization_id, _ID_BYTES, "realization id")
    if len({root_id, cell_id, reusable_id}) != 3:
        _fail("composition object roles must use distinct identities")
    if not 1 <= cell_count <= MAX_CELL_COUNT_V1:
        _fail("composition cell count is outside v1 policy")
    if not 1 <= input_count <= MAX_REALIZATION_INPUTS_V1:
        _fail("composition input count is outside v1 policy")
    if not 0 <= root_slot <= MAX_RELATION_SLOT_V1:
        _fail("composition root slot is outside v1 policy")
    if not 1 <= issued <= project.epoch <= expires <= (1 << 64) - 1:
        _fail("composition is stale or not yet valid for this Object Space epoch")
    if authority != 0 or effects != 0:
        _fail("native cell/reuse composition rejects authority/effect inflation")
    if not 1 <= witness_ceiling <= MAX_WITNESSES:
        _fail("composition reusable witness ceiling is outside v1 policy")
    if not 0 <= max_input <= MAX_ABS_INT64 or not 0 <= max_output <= MAX_ABS_INT64:
        _fail("composition absolute value ceiling is outside signed Int64 policy")

    expected_size = (
        _HEADER.size
        + _OBJECT_COUNT_V1 * _OBJECT.size
        + cell_count * _CELL.size
        + input_count * _BINDING.size
    )
    if len(payload) != expected_size:
        _fail("composition graph count/length relation is non-canonical")

    offset = _HEADER.size
    object_records: list[tuple[bytes, bytes, bytes]] = []
    seen: set[bytes] = set()
    expected_frontends = {
        root_id: NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1,
        cell_id: NATIVE_CELL_FRONTEND_V1,
        reusable_id: NATIVE_REUSABLE_OBJECT_FRONTEND_V1,
    }
    for _ in range(_OBJECT_COUNT_V1):
        object_id, digest, frontend = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        object_id = _exact(object_id, _ID_BYTES, "composition object id")
        digest = _exact(digest, _DIGEST_BYTES, "composition object digest", nonzero=False)
        frontend = _exact(frontend, _FRONTEND_BYTES, "composition object frontend")
        if object_id in seen or object_id not in expected_frontends:
            _fail("composition object table contains duplicate or unknown identity")
        if frontend != expected_frontends[object_id]:
            _fail("composition object frontend identity mismatch")
        seen.add(object_id)
        object_records.append((object_id, digest, frontend))
    if object_records != sorted(object_records, key=lambda item: item[0]):
        _fail("composition object table is not canonical")
    if seen != {root_id, cell_id, reusable_id}:
        _fail("composition object roles are incomplete")

    k0 = {record.object_id: record for record in project.records}
    if set(k0) != seen or set(project.object_payloads) != seen:
        _fail("composition object set differs from sealed k0 authority")
    digest_by_id: dict[bytes, bytes] = {}
    for object_id, digest, _ in object_records:
        if k0[object_id].artifact_digest != digest:
            _fail("composition object digest differs from sealed k0 authority")
        if hashlib.sha256(project.object_payloads[object_id]).digest() != digest:
            _fail("opened composition object digest differs from authenticated authority")
        digest_by_id[object_id] = digest

    cell_records: list[NativeCellRecordV1] = []
    for expected_ordinal in range(cell_count):
        ordinal, tag, domain_code = _CELL.unpack_from(payload, offset)
        offset += _CELL.size
        if ordinal != expected_ordinal:
            _fail("composition cell table is not canonical ordinal order")
        domain = _CODE_TO_DOMAIN.get(domain_code)
        if domain is None:
            _fail("composition cell domain code is invalid")
        cell_records.append(NativeCellRecordV1(ordinal, tag, domain))

    bindings: list[int] = []
    for expected_input in range(input_count):
        input_slot, ordinal, domain_code = _BINDING.unpack_from(payload, offset)
        offset += _BINDING.size
        if input_slot != expected_input:
            _fail("composition reusable input table is not canonical slot order")
        if ordinal >= cell_count:
            _fail("composition input binding references cell outside full schema")
        if _CODE_TO_DOMAIN.get(domain_code) != "whole" or cell_records[ordinal].domain != "whole":
            _fail("composition reusable input binding must reference sealed whole cell")
        bindings.append(ordinal)

    cell_bytes = project.object_payloads[cell_id]
    cell_digest = digest_by_id[cell_id]
    try:
        parsed = _parse_cell_source(_cell_source(cell_bytes))
    except NativeCellRealityError as error:
        raise NativeCellReuseCompositionError(str(error)) from error
    by_tag: dict[bytes, str] = {}
    for name in parsed.resolves:
        tag = _witness_tag(
            project_id=project.project_id,
            root_object_id=cell_id,
            source_digest=cell_digest,
            witness_name=name,
        )
        if tag in by_tag:
            _fail("composition cell witness tag collision during load")
        by_tag[tag] = name
    ordered_names: list[str] = []
    for record in cell_records:
        name = by_tag.get(record.witness_tag)
        if name is None:
            _fail("sealed composition cell does not match resolved source witness")
        ordered_names.append(name)
    if set(ordered_names) != set(parsed.resolves) or len(ordered_names) != len(parsed.resolves):
        _fail("composition cell table does not exactly cover source resolve set")
    try:
        _, cell_values_by_name = _evaluate_cell_source(parsed, ordered_names)
    except NativeCellRealityError as error:
        raise NativeCellReuseCompositionError(str(error)) from error
    cell_values = tuple(cell_values_by_name[name] for name in ordered_names)
    for record, value in zip(cell_records, cell_values):
        if record.domain != value.domain:
            _fail("composition full cell schema domain differs from evaluated source")

    reusable_source = _decode_ascii(project.object_payloads[reusable_id], "composition reusable reality")
    reusable_slots = _template_contract(reusable_source)
    if len(reusable_slots) != input_count:
        _fail("composition input count differs from reusable conduit contract")
    inputs: list[int] = []
    for ordinal in bindings:
        value = cell_values[ordinal]
        if value.domain != "whole":
            _fail("composition projected reusable input is not whole")
        inputs.append(_validate_input(int(value.value), max_abs_input=max_input))
    reusable_check = _materialize_root(
        reusable_source,
        {slot: inputs[index] for index, slot in enumerate(reusable_slots)},
    )
    if len(reusable_check.kernel.witnesses) > witness_ceiling:
        _fail("composition reusable reality exceeds sealed witness ceiling")
    if abs(reusable_check.value) > max_output:
        _fail("composition reusable output exceeds sealed absolute-value ceiling")

    root_source = _decode_ascii(project.object_payloads[root_id], "composition root")
    _validate_root_contract(root_source, root_slot)
    root_check = _materialize_root(root_source, {root_slot: reusable_check.value})
    return NativeCellReuseCompositionCheckV1(
        schema_id=schema_id,
        ordered_cell_witnesses=tuple(ordered_names),
        cell_values=cell_values,
        input_cell_ordinals=tuple(bindings),
        reusable=reusable_check,
        root=root_check,
    )


def check_native_cell_reuse_composition_object_space(project: ObjectSpaceProject):
    checked = decode_native_cell_reuse_composition_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-cell-reuse-composition-root>",
                path=Path("<koschei-native-cell-reuse-composition-root>"),
                program=checked.root.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
