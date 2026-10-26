"""Koschei-native sealed value relationships v1.

A relationship is not a module import.  A leaf Object Space object resolves one
closed immutable witness reality.  A sealed relationship contract may admit that
single resolved value into the root object's witness graph through a local
``conduit`` slot only after object identity, artifact digest, frontend identity,
epoch validity, authority/effect ceilings, and resource ceilings all validate.

There is no target filename, module namespace, source label, runtime lookup, or
API surface.  V1 is deliberately a star: the authenticated root may consume pure
leaf values; leaves cannot themselves consume relationships.  This keeps the
first multi-object native semantic slice auditable before recursive relationship
composition is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import struct
from typing import Mapping, Sequence

from .modules import Module, ModuleGraph, check_graph
from .native_kernel_v1 import (
    MAX_WITNESSES,
    NativeAtom,
    NativeKernel,
    NativeKernelCheck,
    NativeTerm,
    NativeWitness,
    _canonical_source,
    _name,
    check_native_kernel,
    dependency_order,
    evaluate_native_kernel,
    lower_native_kernel,
)
from .object_space_frontend_identity_v1 import NATIVE_WITNESS_FRONTEND_V1
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, MAX_OBJECTS, ObjectSpaceError, ObjectSpaceProject
from .semantic import INT_MAX, SemanticChecker


RELATION_GRAPH_MAGIC_V1 = b"KOSCHEI_OSREL1\x00\x00"
RELATION_GRAPH_VERSION_V1 = 1
_RELATION_FRONTEND_CONTEXT = b"koschei.frontend/native-sealed-value-relationship/v1"
NATIVE_RELATIONSHIP_FRONTEND_V1 = hashlib.sha256(_RELATION_FRONTEND_CONTEXT).digest()
RELATION_WORD_V1 = "conduit"

MAX_RELATIONSHIPS_V1 = 4095
MAX_RELATION_SLOT_V1 = 65535
MAX_ABS_INT64 = 1 << 63
_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32

# magic, version, project id, root object id, object count, relation count
_HEADER = struct.Struct(">16sB7x16s16sII")
# object id, exact digest, frontend identity
_OBJECT = struct.Struct(">16s32s32s")
# relation id, source id, local slot, target id, target digest, target frontend,
# issued epoch, expiry epoch, authority ceiling, effect ceiling,
# target witness ceiling, absolute resolved-value ceiling
_RELATION = struct.Struct(">16s16sI16s32s32sQQQQIQ")


class NativeRelationshipError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class NativeRelationshipSpecV1:
    relation_id: bytes
    slot: int
    target_object_id: bytes
    issued_epoch: int
    expires_epoch: int
    authority_ceiling: int = 0
    effect_ceiling: int = 0
    max_target_witnesses: int = MAX_WITNESSES
    max_abs_value: int = MAX_ABS_INT64


@dataclass(frozen=True, slots=True)
class NativeRelationshipRecordV1:
    relation_id: bytes
    source_object_id: bytes
    slot: int
    target_object_id: bytes
    target_artifact_digest: bytes
    target_frontend_id: bytes
    issued_epoch: int
    expires_epoch: int
    authority_ceiling: int
    effect_ceiling: int
    max_target_witnesses: int
    max_abs_value: int


@dataclass(frozen=True, slots=True)
class NativeRelationshipCheckV1:
    root: NativeKernelCheck
    targets: Mapping[bytes, NativeKernelCheck]
    relations: tuple[NativeRelationshipRecordV1, ...]


def _fail(message: str) -> None:
    raise NativeRelationshipError(message)


def _exact_bytes(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _u64(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= (1 << 64) - 1:
        _fail(f"{label} must be an unsigned 64-bit integer")
    return value


def _positive_epoch(value: object, label: str) -> int:
    epoch = _u64(value, label)
    if epoch < 1:
        _fail(f"{label} must be positive")
    return epoch


def _decode_ascii(payload: bytes, label: str) -> str:
    if not isinstance(payload, bytes):
        _fail(f"{label} payload must be bytes")
    try:
        return payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise NativeRelationshipError(f"{label} payload is not canonical ASCII") from error


def _canonical_objects(objects: Mapping[bytes, bytes]) -> tuple[tuple[bytes, bytes], ...]:
    if not isinstance(objects, Mapping) or not 2 <= len(objects) <= MAX_OBJECTS:
        _fail(f"native relationship v1 requires 2..{MAX_OBJECTS} authoritative objects")
    normalized: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for raw_id, payload in objects.items():
        object_id = _exact_bytes(raw_id, _ID_BYTES, "object id")
        if object_id in seen:
            _fail("duplicate object identity in relationship object map")
        if not isinstance(payload, bytes):
            _fail("relationship object payload must be bytes")
        seen.add(object_id)
        normalized.append((object_id, payload))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def _conduit_slots(source: str) -> tuple[tuple[int, str, int], ...]:
    """Return (slot, witness-name, source-line) while preserving canonical source rules."""

    lines = _canonical_source(source)
    found: list[tuple[int, str, int]] = []
    slots: set[int] = set()
    for line_number, line in enumerate(lines, start=1):
        tokens = line.split(" ")
        if len(tokens) >= 2 and tokens[0] == "witness" and tokens[1] == RELATION_WORD_V1:
            _fail("'conduit' is relationship vocabulary and cannot be a witness identity")
        if len(tokens) == 4 and tokens[0] == "witness" and tokens[2] == RELATION_WORD_V1:
            name = _name(tokens[1], line=line_number)
            raw_slot = tokens[3]
            if not raw_slot.isdigit() or (len(raw_slot) > 1 and raw_slot.startswith("0")):
                _fail("conduit slot must use canonical unsigned decimal spelling")
            if len(raw_slot) > 5:
                _fail("conduit slot exceeds v1 range")
            slot = int(raw_slot)
            if slot > MAX_RELATION_SLOT_V1:
                _fail("conduit slot exceeds v1 range")
            if slot in slots:
                _fail("duplicate conduit slot in root source")
            slots.add(slot)
            found.append((slot, name, line_number))
    return tuple(found)


def _materialize_root(source: str, values_by_slot: Mapping[int, int]) -> NativeKernelCheck:
    lines = list(_canonical_source(source))
    conduits = _conduit_slots(source)
    expected_slots = {slot for slot, _, _ in conduits}
    if expected_slots != set(values_by_slot):
        _fail("root conduit slots do not exactly match sealed relationship slots")

    witness_by_slot = {slot: name for slot, name, _ in conduits}
    replaced_lines: list[str] = []
    for line in lines:
        tokens = line.split(" ")
        if len(tokens) == 4 and tokens[0] == "witness" and tokens[2] == RELATION_WORD_V1:
            replaced_lines.append(f"witness {tokens[1]} 0")
        else:
            if RELATION_WORD_V1 in tokens:
                _fail("'conduit' is valid only as: witness <name> conduit <slot>")
            replaced_lines.append(line)

    # Parse all ordinary native grammar first, using zero only as an internal
    # placeholder.  Then replace those exact witness terms with the authenticated
    # relation values.  This avoids inventing a second arithmetic parser and also
    # supports negative Int64 relationship values without adding negative literal
    # syntax to the native source surface.
    placeholder = check_native_kernel("\n".join(replaced_lines) + "\n")
    replacement_by_name = {
        witness_by_slot[slot]: value for slot, value in values_by_slot.items()
    }
    materialized: list[NativeWitness] = []
    for witness in placeholder.kernel.witnesses:
        if witness.name in replacement_by_name:
            materialized.append(
                replace(
                    witness,
                    term=NativeTerm(
                        None,
                        (NativeAtom(literal=replacement_by_name[witness.name]),),
                    ),
                )
            )
        else:
            materialized.append(witness)
    kernel = replace(placeholder.kernel, witnesses=tuple(materialized))
    lowered = lower_native_kernel(kernel)
    semantic = SemanticChecker(lowered).check()
    return NativeKernelCheck(
        kernel=kernel,
        dependency_order=dependency_order(kernel),
        value=evaluate_native_kernel(kernel),
        lowered=lowered,
        semantic=semantic,
    )


def _validate_spec(
    spec: NativeRelationshipSpecV1,
    *,
    root_object_id: bytes,
    target_digest: bytes,
    current_epoch: int,
    target_check: NativeKernelCheck,
) -> NativeRelationshipRecordV1:
    if not isinstance(spec, NativeRelationshipSpecV1):
        _fail("relationship specification must use NativeRelationshipSpecV1")
    relation_id = _exact_bytes(spec.relation_id, _ID_BYTES, "relationship id")
    target = _exact_bytes(spec.target_object_id, _ID_BYTES, "relationship target object id")
    if not isinstance(spec.slot, int) or isinstance(spec.slot, bool) or not 0 <= spec.slot <= MAX_RELATION_SLOT_V1:
        _fail("relationship slot is outside v1 range")
    issued = _positive_epoch(spec.issued_epoch, "relationship issued epoch")
    expires = _positive_epoch(spec.expires_epoch, "relationship expiry epoch")
    if issued > current_epoch or current_epoch > expires:
        _fail("relationship is stale or not yet valid for the admitted Object Space epoch")
    authority = _u64(spec.authority_ceiling, "relationship authority ceiling")
    effects = _u64(spec.effect_ceiling, "relationship effect ceiling")
    # V1 leaf kernels have no capability/effect surface.  Non-zero ceilings would
    # silently reserve ambient power that no source construct can justify.
    if authority != 0 or effects != 0:
        _fail("native relationship v1 admits only zero authority and zero effect ceilings")
    if (
        not isinstance(spec.max_target_witnesses, int)
        or isinstance(spec.max_target_witnesses, bool)
        or not 1 <= spec.max_target_witnesses <= MAX_WITNESSES
    ):
        _fail("relationship target witness ceiling is outside native v1 bounds")
    if len(target_check.kernel.witnesses) > spec.max_target_witnesses:
        _fail("relationship target exceeds its sealed witness resource ceiling")
    max_abs = _u64(spec.max_abs_value, "relationship absolute value ceiling")
    if max_abs > MAX_ABS_INT64:
        _fail("relationship absolute value ceiling exceeds signed Int64 reality")
    if abs(target_check.value) > max_abs:
        _fail("relationship resolved value exceeds its sealed resource ceiling")

    return NativeRelationshipRecordV1(
        relation_id=relation_id,
        source_object_id=root_object_id,
        slot=spec.slot,
        target_object_id=target,
        target_artifact_digest=target_digest,
        target_frontend_id=NATIVE_WITNESS_FRONTEND_V1,
        issued_epoch=issued,
        expires_epoch=expires,
        authority_ceiling=authority,
        effect_ceiling=effects,
        max_target_witnesses=spec.max_target_witnesses,
        max_abs_value=max_abs,
    )


def encode_native_relationship_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    current_epoch: int,
    relationships: Sequence[NativeRelationshipSpecV1],
) -> bytes:
    project = _exact_bytes(project_id, _ID_BYTES, "project id")
    root = _exact_bytes(root_object_id, _ID_BYTES, "root object id")
    epoch = _positive_epoch(current_epoch, "current Object Space epoch")
    canonical = _canonical_objects(objects)
    object_payloads = dict(canonical)
    if root not in object_payloads:
        _fail("relationship root object is absent")
    if not isinstance(relationships, Sequence) or isinstance(relationships, (str, bytes)):
        _fail("relationships must be an ordered sequence")
    if not 1 <= len(relationships) <= MAX_RELATIONSHIPS_V1:
        _fail(f"relationship count must be 1..{MAX_RELATIONSHIPS_V1}")

    targets: dict[bytes, NativeKernelCheck] = {}
    digests = {object_id: hashlib.sha256(payload).digest() for object_id, payload in canonical}
    for object_id, payload in canonical:
        if object_id == root:
            continue
        checked = check_native_kernel(_decode_ascii(payload, "relationship target"))
        if any(witness.name == RELATION_WORD_V1 for witness in checked.kernel.witnesses):
            _fail("'conduit' is reserved relationship vocabulary in native relationship projects")
        targets[object_id] = checked

    records: list[NativeRelationshipRecordV1] = []
    seen_relations: set[bytes] = set()
    seen_slots: set[int] = set()
    seen_targets: set[bytes] = set()
    for spec in relationships:
        target_id = _exact_bytes(spec.target_object_id, _ID_BYTES, "relationship target object id")
        if target_id == root or target_id not in targets:
            _fail("relationship target must be a non-root authoritative native object")
        record = _validate_spec(
            spec,
            root_object_id=root,
            target_digest=digests[target_id],
            current_epoch=epoch,
            target_check=targets[target_id],
        )
        if record.relation_id in seen_relations:
            _fail("duplicate relationship identity")
        if record.slot in seen_slots:
            _fail("duplicate relationship slot")
        if record.target_object_id in seen_targets:
            _fail("native relationship v1 admits one sealed value edge per leaf object")
        seen_relations.add(record.relation_id)
        seen_slots.add(record.slot)
        seen_targets.add(record.target_object_id)
        records.append(record)

    # Every physical/authenticated leaf must participate, and every source conduit
    # must have exactly one sealed relation.  Hidden edges and orphan objects fail.
    if seen_targets != set(targets):
        _fail("native relationship graph contains an orphan leaf or missing relation")
    root_source = _decode_ascii(object_payloads[root], "relationship root")
    root_slots = {slot for slot, _, _ in _conduit_slots(root_source)}
    if root_slots != seen_slots:
        _fail("root conduit set does not exactly match sealed relationship slots")

    values = {record.slot: targets[record.target_object_id].value for record in records}
    _materialize_root(root_source, values)

    object_records: list[tuple[bytes, bytes, bytes]] = []
    for object_id, _ in canonical:
        frontend = (
            NATIVE_RELATIONSHIP_FRONTEND_V1 if object_id == root else NATIVE_WITNESS_FRONTEND_V1
        )
        object_records.append((object_id, digests[object_id], frontend))
    records.sort(key=lambda item: (item.source_object_id, item.slot, item.relation_id))

    body = bytearray(
        _HEADER.pack(
            RELATION_GRAPH_MAGIC_V1,
            RELATION_GRAPH_VERSION_V1,
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
            _RELATION.pack(
                record.relation_id,
                record.source_object_id,
                record.slot,
                record.target_object_id,
                record.target_artifact_digest,
                record.target_frontend_id,
                record.issued_epoch,
                record.expires_epoch,
                record.authority_ceiling,
                record.effect_ceiling,
                record.max_target_witnesses,
                record.max_abs_value,
            )
        )
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("native relationship graph exceeds sealed graph byte budget")
    return bytes(body)


def is_native_relationship_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(RELATION_GRAPH_MAGIC_V1)


def decode_native_relationship_graph(project: ObjectSpaceProject) -> NativeRelationshipCheckV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native relationships require a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) < _HEADER.size or len(payload) > MAX_GRAPH_SECRET_BYTES:
        _fail("native relationship graph length is invalid")

    magic, version, project_id, root_id, object_count, relation_count = _HEADER.unpack_from(payload, 0)
    if magic != RELATION_GRAPH_MAGIC_V1 or version != RELATION_GRAPH_VERSION_V1:
        _fail("native relationship graph schema is invalid")
    if project_id != project.project_id:
        _fail("native relationship graph belongs to another project")
    if root_id != project.root_object_id:
        _fail("native relationship graph root identity mismatch")
    if not 2 <= object_count <= MAX_OBJECTS or not 1 <= relation_count <= MAX_RELATIONSHIPS_V1:
        _fail("native relationship graph counts are outside policy")
    expected_size = _HEADER.size + object_count * _OBJECT.size + relation_count * _RELATION.size
    if len(payload) != expected_size:
        _fail("native relationship graph count/length relation is non-canonical")

    offset = _HEADER.size
    object_records: list[tuple[bytes, bytes, bytes]] = []
    seen_objects: set[bytes] = set()
    for _ in range(object_count):
        object_id, digest, frontend_id = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        object_id = _exact_bytes(object_id, _ID_BYTES, "relationship object id")
        digest = _exact_bytes(digest, _DIGEST_BYTES, "relationship object digest", nonzero=False)
        frontend_id = _exact_bytes(frontend_id, _FRONTEND_BYTES, "relationship frontend identity")
        if object_id in seen_objects:
            _fail("duplicate object identity in native relationship graph")
        expected_frontend = NATIVE_RELATIONSHIP_FRONTEND_V1 if object_id == root_id else NATIVE_WITNESS_FRONTEND_V1
        if frontend_id != expected_frontend:
            _fail("native relationship object frontend identity mismatch")
        seen_objects.add(object_id)
        object_records.append((object_id, digest, frontend_id))
    if object_records != sorted(object_records, key=lambda item: item[0]):
        _fail("native relationship object table is not canonical")

    k0_by_id = {record.object_id: record for record in project.records}
    if set(k0_by_id) != seen_objects or set(project.object_payloads) != seen_objects:
        _fail("native relationship object set differs from sealed k0 authority")
    digest_by_id: dict[bytes, bytes] = {}
    for object_id, digest, _ in object_records:
        if k0_by_id[object_id].artifact_digest != digest:
            _fail("native relationship object digest differs from sealed k0 authority")
        payload_bytes = project.object_payloads[object_id]
        if hashlib.sha256(payload_bytes).digest() != digest:
            _fail("opened relationship object digest differs from authenticated authority")
        digest_by_id[object_id] = digest

    relations: list[NativeRelationshipRecordV1] = []
    seen_relation_ids: set[bytes] = set()
    seen_slots: set[int] = set()
    seen_targets: set[bytes] = set()
    for _ in range(relation_count):
        unpacked = _RELATION.unpack_from(payload, offset)
        offset += _RELATION.size
        record = NativeRelationshipRecordV1(*unpacked)
        relation_id = _exact_bytes(record.relation_id, _ID_BYTES, "relationship id")
        source_id = _exact_bytes(record.source_object_id, _ID_BYTES, "relationship source id")
        target_id = _exact_bytes(record.target_object_id, _ID_BYTES, "relationship target id")
        target_digest = _exact_bytes(record.target_artifact_digest, _DIGEST_BYTES, "relationship target digest", nonzero=False)
        target_frontend = _exact_bytes(record.target_frontend_id, _FRONTEND_BYTES, "relationship target frontend")
        if source_id != root_id or target_id == root_id or target_id not in seen_objects:
            _fail("native relationship edge is not a root-to-leaf relationship")
        if target_frontend != NATIVE_WITNESS_FRONTEND_V1:
            _fail("native relationship target frontend is not the witness frontend")
        if target_digest != digest_by_id[target_id]:
            _fail("native relationship target digest mismatch")
        if relation_id in seen_relation_ids or record.slot in seen_slots or target_id in seen_targets:
            _fail("duplicate relationship identity, slot, or target")
        if not 0 <= record.slot <= MAX_RELATION_SLOT_V1:
            _fail("relationship slot is outside v1 range")
        if not (1 <= record.issued_epoch <= project.epoch <= record.expires_epoch <= (1 << 64) - 1):
            _fail("relationship is stale or not yet valid for this Object Space epoch")
        if record.authority_ceiling != 0 or record.effect_ceiling != 0:
            _fail("native relationship v1 rejects authority/effect inflation")
        if not 1 <= record.max_target_witnesses <= MAX_WITNESSES:
            _fail("relationship witness ceiling is outside v1 policy")
        if not 0 <= record.max_abs_value <= MAX_ABS_INT64:
            _fail("relationship absolute value ceiling is outside v1 policy")
        seen_relation_ids.add(relation_id)
        seen_slots.add(record.slot)
        seen_targets.add(target_id)
        relations.append(record)
    if relations != sorted(relations, key=lambda item: (item.source_object_id, item.slot, item.relation_id)):
        _fail("native relationship table is not canonical")
    if seen_targets != (seen_objects - {root_id}):
        _fail("native relationship graph contains an orphan or hidden leaf")

    target_checks: dict[bytes, NativeKernelCheck] = {}
    for target_id in seen_targets:
        checked = check_native_kernel(_decode_ascii(project.object_payloads[target_id], "relationship target"))
        if any(witness.name == RELATION_WORD_V1 for witness in checked.kernel.witnesses):
            _fail("'conduit' is reserved relationship vocabulary in relationship projects")
        record = next(item for item in relations if item.target_object_id == target_id)
        if len(checked.kernel.witnesses) > record.max_target_witnesses:
            _fail("relationship target exceeds its sealed witness resource ceiling")
        if abs(checked.value) > record.max_abs_value:
            _fail("relationship resolved value exceeds its sealed resource ceiling")
        target_checks[target_id] = checked

    root_source = _decode_ascii(project.object_payloads[root_id], "relationship root")
    source_slots = {slot for slot, _, _ in _conduit_slots(root_source)}
    if source_slots != seen_slots:
        _fail("root conduit set does not exactly match sealed relationship slots")
    values = {item.slot: target_checks[item.target_object_id].value for item in relations}
    root_check = _materialize_root(root_source, values)
    return NativeRelationshipCheckV1(root_check, target_checks, tuple(relations))


def check_native_relationship_object_space(project: ObjectSpaceProject):
    """Validate all related objects, then lower the materialized root to existing MIR.

    Leaf objects are compile-time immutable value realities. Their resolved values
    are sealed-link inputs, not runtime module APIs, so the backend graph contains
    only the materialized root program. The returned relationship check remains
    available separately through ``decode_native_relationship_graph`` for audit.
    """

    checked = decode_native_relationship_graph(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-relationship-root>",
                path=Path("<koschei-native-relationship-root>"),
                program=checked.root.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
