"""Koschei-native sealed reusable realities v1.

Reuse is not modeled as a function declaration/call/parameter surface.  A reusable
object is one immutable witness graph with numbered ``conduit`` input apertures.
The source object exists once in Object Space.  Authenticated realization records
may bind that same canonical object to different Int64 input vectors and admit
each resolved value into a conduit slot of one root reality.

V1 is deliberately pure and Whole/Int64-only.  It proves the identity/reuse model
before adding richer value-domain inputs, recursive realization DAGs, effects or
authority.  No source keyword is added beyond the already-native ``conduit``
relationship vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping, Sequence

from .modules import Module, ModuleGraph, check_graph
from .native_kernel_v1 import MAX_WITNESSES, NativeKernelCheck
from .native_relationship_v1 import (
    MAX_ABS_INT64,
    MAX_RELATION_SLOT_V1,
    NATIVE_RELATIONSHIP_FRONTEND_V1,
    _conduit_slots,
    _decode_ascii,
    _exact_bytes,
    _materialize_root,
    _positive_epoch,
    _u64,
)
from .object_space_frontend_identity_v1 import NATIVE_WITNESS_FRONTEND_V1
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, MAX_OBJECTS, ObjectSpaceError, ObjectSpaceProject


REUSABLE_GRAPH_MAGIC_V1 = b"KOSCHEI_OSREUSE1"
REUSABLE_GRAPH_VERSION_V1 = 1
_REUSABLE_ROOT_CONTEXT = b"koschei.frontend/native-reusable-root/v1"
_REUSABLE_OBJECT_CONTEXT = b"koschei.frontend/native-reusable-reality/v1"
NATIVE_REUSABLE_ROOT_FRONTEND_V1 = hashlib.sha256(_REUSABLE_ROOT_CONTEXT).digest()
NATIVE_REUSABLE_OBJECT_FRONTEND_V1 = hashlib.sha256(_REUSABLE_OBJECT_CONTEXT).digest()

MAX_REALIZATIONS_V1 = 4095
MAX_REALIZATION_INPUTS_V1 = 64
MAX_TOTAL_REALIZATION_INPUTS_V1 = 65536
_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32

# magic, version, project id, root object id, object count, realization count
_HEADER = struct.Struct(">16sB7x16s16sII")
# object id, digest, frontend identity
_OBJECT = struct.Struct(">16s32s32s")
# realization id, root conduit slot, reusable object id, reusable digest/frontend,
# input count, witness ceiling, abs-input ceiling, abs-output ceiling,
# issued/expiry epoch, authority/effect ceilings
_REALIZATION = struct.Struct(">16sI16s32s32sIIQQQQQQ")
_INPUT = struct.Struct(">q")


class NativeReusableRealityError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeReusableRealizationSpecV1:
    realization_id: bytes
    root_slot: int
    reusable_object_id: bytes
    inputs: tuple[int, ...]
    issued_epoch: int
    expires_epoch: int
    max_reusable_witnesses: int = MAX_WITNESSES
    max_abs_input: int = MAX_ABS_INT64
    max_abs_output: int = MAX_ABS_INT64
    authority_ceiling: int = 0
    effect_ceiling: int = 0


@dataclass(frozen=True, slots=True)
class NativeReusableRealizationRecordV1:
    realization_id: bytes
    root_slot: int
    reusable_object_id: bytes
    reusable_artifact_digest: bytes
    reusable_frontend_id: bytes
    inputs: tuple[int, ...]
    max_reusable_witnesses: int
    max_abs_input: int
    max_abs_output: int
    issued_epoch: int
    expires_epoch: int
    authority_ceiling: int
    effect_ceiling: int


@dataclass(frozen=True, slots=True)
class NativeReusableRealityCheckV1:
    root: NativeKernelCheck
    reusable_objects: Mapping[bytes, tuple[str, tuple[int, ...]]]
    realized: Mapping[bytes, NativeKernelCheck]
    realizations: tuple[NativeReusableRealizationRecordV1, ...]


def _fail(message: str) -> None:
    raise NativeReusableRealityError(message)


def _canonical_objects(objects: Mapping[bytes, bytes]) -> tuple[tuple[bytes, bytes], ...]:
    if not isinstance(objects, Mapping) or not 2 <= len(objects) <= MAX_OBJECTS:
        _fail(f"native reusable realities require 2..{MAX_OBJECTS} authoritative objects")
    result: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for raw_id, payload in objects.items():
        object_id = _exact_bytes(raw_id, _ID_BYTES, "reusable object id")
        if object_id in seen:
            _fail("duplicate object identity in reusable reality object map")
        if not isinstance(payload, bytes):
            _fail("reusable reality payload must be bytes")
        seen.add(object_id)
        result.append((object_id, payload))
    result.sort(key=lambda item: item[0])
    return tuple(result)


def _template_contract(source: str) -> tuple[int, ...]:
    slots = tuple(sorted(slot for slot, _, _ in _conduit_slots(source)))
    if not slots:
        _fail("reusable reality must expose at least one conduit input")
    if len(slots) > MAX_REALIZATION_INPUTS_V1:
        _fail("reusable reality exposes too many conduit inputs for v1")
    expected = tuple(range(len(slots)))
    if slots != expected:
        _fail("reusable reality conduit inputs must be contiguous from slot 0")
    return slots


def _validate_input(value: object, *, max_abs_input: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail("reusable realization inputs must be signed Int64 values")
    if not -(1 << 63) <= value <= (1 << 63) - 1:
        _fail("reusable realization input exceeds signed Int64 reality")
    if abs(value) > max_abs_input:
        _fail("reusable realization input exceeds its sealed absolute-value ceiling")
    return value


def _validate_spec(
    spec: NativeReusableRealizationSpecV1,
    *,
    root_object_id: bytes,
    reusable_digest: bytes,
    reusable_source: str,
    current_epoch: int,
) -> tuple[NativeReusableRealizationRecordV1, NativeKernelCheck]:
    if not isinstance(spec, NativeReusableRealizationSpecV1):
        _fail("realization specification must use NativeReusableRealizationSpecV1")
    realization_id = _exact_bytes(spec.realization_id, _ID_BYTES, "realization id")
    reusable_id = _exact_bytes(spec.reusable_object_id, _ID_BYTES, "reusable object id")
    if reusable_id == root_object_id:
        _fail("root reality cannot be realized as its own reusable object")
    if not isinstance(spec.root_slot, int) or isinstance(spec.root_slot, bool) or not 0 <= spec.root_slot <= MAX_RELATION_SLOT_V1:
        _fail("realization root slot is outside v1 range")
    if not isinstance(spec.inputs, tuple) or not 1 <= len(spec.inputs) <= MAX_REALIZATION_INPUTS_V1:
        _fail("realization input vector is outside v1 bounds")

    issued = _positive_epoch(spec.issued_epoch, "realization issued epoch")
    expires = _positive_epoch(spec.expires_epoch, "realization expiry epoch")
    if issued > current_epoch or current_epoch > expires:
        _fail("realization is stale or not yet valid for this Object Space epoch")

    authority = _u64(spec.authority_ceiling, "realization authority ceiling")
    effects = _u64(spec.effect_ceiling, "realization effect ceiling")
    if authority != 0 or effects != 0:
        _fail("native reusable reality v1 admits only zero authority and zero effects")

    if (
        not isinstance(spec.max_reusable_witnesses, int)
        or isinstance(spec.max_reusable_witnesses, bool)
        or not 1 <= spec.max_reusable_witnesses <= MAX_WITNESSES
    ):
        _fail("reusable witness ceiling is outside native v1 bounds")
    max_input = _u64(spec.max_abs_input, "realization absolute input ceiling")
    max_output = _u64(spec.max_abs_output, "realization absolute output ceiling")
    if max_input > MAX_ABS_INT64 or max_output > MAX_ABS_INT64:
        _fail("realization absolute value ceiling exceeds signed Int64 reality")

    slots = _template_contract(reusable_source)
    if len(spec.inputs) != len(slots):
        _fail("realization input vector length does not match reusable conduit contract")
    values = {
        slot: _validate_input(spec.inputs[slot], max_abs_input=max_input)
        for slot in slots
    }
    checked = _materialize_root(reusable_source, values)
    if len(checked.kernel.witnesses) > spec.max_reusable_witnesses:
        _fail("reusable reality exceeds its sealed witness resource ceiling")
    if abs(checked.value) > max_output:
        _fail("reusable realization output exceeds its sealed absolute-value ceiling")

    return (
        NativeReusableRealizationRecordV1(
            realization_id=realization_id,
            root_slot=spec.root_slot,
            reusable_object_id=reusable_id,
            reusable_artifact_digest=reusable_digest,
            reusable_frontend_id=NATIVE_REUSABLE_OBJECT_FRONTEND_V1,
            inputs=tuple(values[index] for index in slots),
            max_reusable_witnesses=spec.max_reusable_witnesses,
            max_abs_input=max_input,
            max_abs_output=max_output,
            issued_epoch=issued,
            expires_epoch=expires,
            authority_ceiling=authority,
            effect_ceiling=effects,
        ),
        checked,
    )


def encode_native_reusable_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    current_epoch: int,
    realizations: Sequence[NativeReusableRealizationSpecV1],
) -> bytes:
    project = _exact_bytes(project_id, _ID_BYTES, "project id")
    root = _exact_bytes(root_object_id, _ID_BYTES, "root object id")
    epoch = _positive_epoch(current_epoch, "current Object Space epoch")
    canonical = _canonical_objects(objects)
    payloads = dict(canonical)
    if root not in payloads:
        _fail("reusable root object is absent")
    if not isinstance(realizations, Sequence) or isinstance(realizations, (str, bytes)):
        _fail("realizations must be an ordered sequence")
    if not 1 <= len(realizations) <= MAX_REALIZATIONS_V1:
        _fail(f"realization count must be 1..{MAX_REALIZATIONS_V1}")

    digests = {object_id: hashlib.sha256(payload).digest() for object_id, payload in canonical}
    reusable_sources: dict[bytes, str] = {}
    for object_id, payload in canonical:
        if object_id == root:
            continue
        source = _decode_ascii(payload, "reusable reality")
        _template_contract(source)
        reusable_sources[object_id] = source

    records: list[NativeReusableRealizationRecordV1] = []
    realized: dict[bytes, NativeKernelCheck] = {}
    seen_ids: set[bytes] = set()
    seen_root_slots: set[int] = set()
    referenced_objects: set[bytes] = set()
    total_inputs = 0
    for spec in realizations:
        reusable_id = _exact_bytes(spec.reusable_object_id, _ID_BYTES, "reusable realization object id")
        if reusable_id not in reusable_sources:
            _fail("realization target must be a non-root authoritative reusable object")
        record, checked = _validate_spec(
            spec,
            root_object_id=root,
            reusable_digest=digests[reusable_id],
            reusable_source=reusable_sources[reusable_id],
            current_epoch=epoch,
        )
        if record.realization_id in seen_ids:
            _fail("duplicate reusable realization identity")
        if record.root_slot in seen_root_slots:
            _fail("duplicate reusable realization root slot")
        total_inputs += len(record.inputs)
        if total_inputs > MAX_TOTAL_REALIZATION_INPUTS_V1:
            _fail("reusable realization graph exceeds total input budget")
        seen_ids.add(record.realization_id)
        seen_root_slots.add(record.root_slot)
        referenced_objects.add(record.reusable_object_id)
        records.append(record)
        realized[record.realization_id] = checked

    # A canonical reusable object may be realized many times, but dormant physical
    # reusable objects are not admitted.  This is the core difference from the
    # one-target-per-leaf relationship contract.
    if referenced_objects != set(reusable_sources):
        _fail("reusable graph contains an orphan reusable object")

    root_source = _decode_ascii(payloads[root], "reusable root")
    root_slots = {slot for slot, _, _ in _conduit_slots(root_source)}
    if root_slots != seen_root_slots:
        _fail("root conduit set does not exactly match reusable realization slots")
    values = {record.root_slot: realized[record.realization_id].value for record in records}
    _materialize_root(root_source, values)

    object_records: list[tuple[bytes, bytes, bytes]] = []
    for object_id, _ in canonical:
        frontend = NATIVE_REUSABLE_ROOT_FRONTEND_V1 if object_id == root else NATIVE_REUSABLE_OBJECT_FRONTEND_V1
        object_records.append((object_id, digests[object_id], frontend))
    records.sort(key=lambda item: (item.root_slot, item.realization_id))

    body = bytearray(
        _HEADER.pack(
            REUSABLE_GRAPH_MAGIC_V1,
            REUSABLE_GRAPH_VERSION_V1,
            project,
            root,
            len(object_records),
            len(records),
        )
    )
    for item in object_records:
        body.extend(_OBJECT.pack(*item))
    for record in records:
        body.extend(
            _REALIZATION.pack(
                record.realization_id,
                record.root_slot,
                record.reusable_object_id,
                record.reusable_artifact_digest,
                record.reusable_frontend_id,
                len(record.inputs),
                record.max_reusable_witnesses,
                record.max_abs_input,
                record.max_abs_output,
                record.issued_epoch,
                record.expires_epoch,
                record.authority_ceiling,
                record.effect_ceiling,
            )
        )
        for value in record.inputs:
            body.extend(_INPUT.pack(value))
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("native reusable graph exceeds sealed graph byte budget")
    return bytes(body)


def is_native_reusable_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(REUSABLE_GRAPH_MAGIC_V1)


def decode_native_reusable_graph(project: ObjectSpaceProject) -> NativeReusableRealityCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native reusable realities require a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size or len(payload) > MAX_GRAPH_SECRET_BYTES:
        _fail("native reusable graph length is invalid")

    magic, version, project_id, root_id, object_count, realization_count = _HEADER.unpack_from(payload, 0)
    if magic != REUSABLE_GRAPH_MAGIC_V1 or version != REUSABLE_GRAPH_VERSION_V1:
        _fail("native reusable graph schema is invalid")
    if project_id != project.project_id:
        _fail("native reusable graph belongs to another project")
    if root_id != project.root_object_id:
        _fail("native reusable graph root identity mismatch")
    if not 2 <= object_count <= MAX_OBJECTS or not 1 <= realization_count <= MAX_REALIZATIONS_V1:
        _fail("native reusable graph counts are outside v1 policy")

    minimum = _HEADER.size + object_count * _OBJECT.size + realization_count * _REALIZATION.size
    if len(payload) < minimum:
        _fail("native reusable graph is truncated")

    offset = _HEADER.size
    objects: list[tuple[bytes, bytes, bytes]] = []
    seen_objects: set[bytes] = set()
    for _ in range(object_count):
        object_id, digest, frontend = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        object_id = _exact_bytes(object_id, _ID_BYTES, "reusable graph object id")
        digest = _exact_bytes(digest, _DIGEST_BYTES, "reusable graph object digest", nonzero=False)
        frontend = _exact_bytes(frontend, _FRONTEND_BYTES, "reusable graph frontend identity")
        if object_id in seen_objects:
            _fail("duplicate object identity in reusable graph")
        expected = NATIVE_REUSABLE_ROOT_FRONTEND_V1 if object_id == root_id else NATIVE_REUSABLE_OBJECT_FRONTEND_V1
        if frontend != expected:
            _fail("reusable graph object frontend identity mismatch")
        seen_objects.add(object_id)
        objects.append((object_id, digest, frontend))
    if objects != sorted(objects, key=lambda item: item[0]):
        _fail("reusable graph object table is not canonical")

    k0_by_id = {record.object_id: record for record in project.records}
    if set(k0_by_id) != seen_objects or set(project.object_payloads) != seen_objects:
        _fail("reusable graph object set differs from sealed k0 authority")
    digest_by_id: dict[bytes, bytes] = {}
    for object_id, digest, _ in objects:
        if k0_by_id[object_id].artifact_digest != digest:
            _fail("reusable graph digest differs from sealed k0 authority")
        if hashlib.sha256(project.object_payloads[object_id]).digest() != digest:
            _fail("opened reusable object digest differs from authenticated authority")
        digest_by_id[object_id] = digest

    reusable_sources: dict[bytes, str] = {}
    reusable_contracts: dict[bytes, tuple[int, ...]] = {}
    for object_id in seen_objects - {root_id}:
        source = _decode_ascii(project.object_payloads[object_id], "reusable reality")
        reusable_sources[object_id] = source
        reusable_contracts[object_id] = _template_contract(source)

    records: list[NativeReusableRealizationRecordV1] = []
    realized: dict[bytes, NativeKernelCheck] = {}
    seen_ids: set[bytes] = set()
    seen_root_slots: set[int] = set()
    referenced_objects: set[bytes] = set()
    total_inputs = 0
    for _ in range(realization_count):
        if offset + _REALIZATION.size > len(payload):
            _fail("native reusable realization table is truncated")
        unpacked = _REALIZATION.unpack_from(payload, offset)
        offset += _REALIZATION.size
        (
            realization_id,
            root_slot,
            reusable_id,
            reusable_digest,
            reusable_frontend,
            input_count,
            witness_ceiling,
            max_input,
            max_output,
            issued,
            expires,
            authority,
            effects,
        ) = unpacked
        realization_id = _exact_bytes(realization_id, _ID_BYTES, "realization id")
        reusable_id = _exact_bytes(reusable_id, _ID_BYTES, "realized object id")
        reusable_digest = _exact_bytes(reusable_digest, _DIGEST_BYTES, "realized object digest", nonzero=False)
        reusable_frontend = _exact_bytes(reusable_frontend, _FRONTEND_BYTES, "realized object frontend")
        if reusable_id == root_id or reusable_id not in reusable_sources:
            _fail("realization references a non-reusable authoritative object")
        if reusable_digest != digest_by_id[reusable_id] or reusable_frontend != NATIVE_REUSABLE_OBJECT_FRONTEND_V1:
            _fail("realization target digest/frontend contract mismatch")
        if realization_id in seen_ids or root_slot in seen_root_slots:
            _fail("duplicate realization identity or root slot")
        if not 0 <= root_slot <= MAX_RELATION_SLOT_V1:
            _fail("realization root slot is outside v1 range")
        if not 1 <= input_count <= MAX_REALIZATION_INPUTS_V1:
            _fail("realization input count is outside v1 bounds")
        if input_count != len(reusable_contracts[reusable_id]):
            _fail("realization input count differs from reusable conduit contract")
        total_inputs += input_count
        if total_inputs > MAX_TOTAL_REALIZATION_INPUTS_V1:
            _fail("reusable graph exceeds total input budget")
        if offset + input_count * _INPUT.size > len(payload):
            _fail("native reusable realization input vector is truncated")
        inputs = tuple(_INPUT.unpack_from(payload, offset + index * _INPUT.size)[0] for index in range(input_count))
        offset += input_count * _INPUT.size

        if not 1 <= issued <= project.epoch <= expires <= (1 << 64) - 1:
            _fail("realization is stale or not yet valid for this Object Space epoch")
        if authority != 0 or effects != 0:
            _fail("native reusable v1 rejects authority/effect inflation")
        if not 1 <= witness_ceiling <= MAX_WITNESSES:
            _fail("realization witness ceiling is outside v1 bounds")
        if not 0 <= max_input <= MAX_ABS_INT64 or not 0 <= max_output <= MAX_ABS_INT64:
            _fail("realization absolute value ceiling is outside signed Int64 policy")
        values = {
            slot: _validate_input(inputs[slot], max_abs_input=max_input)
            for slot in reusable_contracts[reusable_id]
        }
        checked = _materialize_root(reusable_sources[reusable_id], values)
        if len(checked.kernel.witnesses) > witness_ceiling:
            _fail("reusable reality exceeds sealed witness ceiling")
        if abs(checked.value) > max_output:
            _fail("reusable realization output exceeds sealed absolute-value ceiling")

        record = NativeReusableRealizationRecordV1(
            realization_id=realization_id,
            root_slot=root_slot,
            reusable_object_id=reusable_id,
            reusable_artifact_digest=reusable_digest,
            reusable_frontend_id=reusable_frontend,
            inputs=inputs,
            max_reusable_witnesses=witness_ceiling,
            max_abs_input=max_input,
            max_abs_output=max_output,
            issued_epoch=issued,
            expires_epoch=expires,
            authority_ceiling=authority,
            effect_ceiling=effects,
        )
        seen_ids.add(realization_id)
        seen_root_slots.add(root_slot)
        referenced_objects.add(reusable_id)
        records.append(record)
        realized[realization_id] = checked

    if offset != len(payload):
        _fail("native reusable graph contains trailing or non-canonical bytes")
    if records != sorted(records, key=lambda item: (item.root_slot, item.realization_id)):
        _fail("native reusable realization table is not canonical")
    if referenced_objects != set(reusable_sources):
        _fail("reusable graph contains an orphan reusable object")

    root_source = _decode_ascii(project.object_payloads[root_id], "reusable root")
    root_slots = {slot for slot, _, _ in _conduit_slots(root_source)}
    if root_slots != seen_root_slots:
        _fail("root conduit set does not exactly match reusable realization slots")
    values = {record.root_slot: realized[record.realization_id].value for record in records}
    root_check = _materialize_root(root_source, values)

    reusable_audit = {
        object_id: (source, reusable_contracts[object_id])
        for object_id, source in reusable_sources.items()
    }
    return NativeReusableRealityCheckV1(root_check, reusable_audit, realized, tuple(records))


def check_native_reusable_object_space(project: ObjectSpaceProject):
    checked = decode_native_reusable_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-reusable-root>",
                path=Path("<koschei-native-reusable-root>"),
                program=checked.root.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
