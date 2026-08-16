"""Authenticated frontend identity for Koschei Object Space.

Frontend selection is authority, not syntax sniffing.  A native source object is
parsed by the native frontend only when the sealed Object Space graph binds that
object to the exact native frontend identity.  Filenames, extensions, plaintext
prefixes and parser success/failure never select a frontend.

V1 deliberately admits one native object only.  Koschei-native inter-object
relationship semantics do not exist yet; reusing legacy ``import`` merely to get
multi-object support would make the migration cosmetic rather than semantic.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping

from .modules import Module, ModuleGraph, check_graph
from .native_kernel_v1 import NativeKernelCheck, check_native_kernel
from .object_space_graph_v1 import check_object_space_graph as _legacy_check_object_space_graph
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, MAX_OBJECTS, ObjectSpaceError, ObjectSpaceProject


FRONTEND_GRAPH_MAGIC_V1 = b"KOSCHEI_OSFRONT1"
FRONTEND_GRAPH_VERSION_V1 = 1
_FRONTEND_ID_CONTEXT = b"koschei.frontend/native-witness-graph/v1"
NATIVE_WITNESS_FRONTEND_V1 = hashlib.sha256(_FRONTEND_ID_CONTEXT).digest()

_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32

# magic, version, project id, root object id, object count
_HEADER = struct.Struct(">16sB7x16s16sI4x")
# object id, exact artifact digest, frontend identity
_OBJECT = struct.Struct(">16s32s32s")


class ObjectSpaceFrontendIdentityError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class FrontendObjectRecordV1:
    object_id: bytes
    artifact_digest: bytes
    frontend_id: bytes


def _fail(message: str) -> None:
    raise ObjectSpaceFrontendIdentityError(message)


def _exact_bytes(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _project_objects(objects: Mapping[bytes, bytes]) -> tuple[tuple[bytes, bytes], ...]:
    if not isinstance(objects, Mapping) or not objects or len(objects) > MAX_OBJECTS:
        _fail(f"frontend object map must contain 1..{MAX_OBJECTS} objects")
    normalized: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for raw_id, payload in objects.items():
        object_id = _exact_bytes(raw_id, _ID_BYTES, "object id")
        if object_id in seen:
            _fail("frontend object map contains duplicate object identity")
        if not isinstance(payload, bytes):
            _fail("frontend object payload must be bytes")
        seen.add(object_id)
        normalized.append((object_id, payload))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def _native_source(payload: bytes) -> str:
    try:
        return payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ObjectSpaceFrontendIdentityError(
            "native frontend payload is not canonical ASCII"
        ) from error


def _require_supported_frontend(frontend_id: object) -> bytes:
    identity = _exact_bytes(frontend_id, _FRONTEND_BYTES, "frontend identity")
    if identity != NATIVE_WITNESS_FRONTEND_V1:
        _fail("sealed graph names an unsupported frontend identity")
    return identity


def is_authenticated_frontend_graph_secret(payload: object) -> bool:
    """Return only a routing hint from authenticated graph bytes.

    Callers must still decode/validate the complete schema.  The dispatcher uses
    this marker after Object Space has already opened sealed k0; source bytes are
    never consulted for frontend selection.
    """

    return isinstance(payload, bytes) and payload.startswith(FRONTEND_GRAPH_MAGIC_V1)


def encode_authenticated_frontend_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
    frontend_by_object: Mapping[bytes, bytes],
) -> bytes:
    """Create canonical sealed-graph metadata for an explicit frontend binding."""

    project = _exact_bytes(project_id, _ID_BYTES, "project id")
    root = _exact_bytes(root_object_id, _ID_BYTES, "root object id")
    canonical = _project_objects(objects)
    object_ids = {object_id for object_id, _ in canonical}
    if root not in object_ids:
        _fail("frontend graph root object is absent")
    if not isinstance(frontend_by_object, Mapping):
        _fail("frontend binding must be a mapping")
    if set(frontend_by_object) != object_ids:
        _fail("frontend binding object set must exactly match authoritative objects")

    # V1 is intentionally single-object until native relationship slots exist.
    if len(canonical) != 1 or canonical[0][0] != root:
        _fail("native frontend v1 requires exactly one authoritative root object")

    records: list[FrontendObjectRecordV1] = []
    for object_id, payload in canonical:
        frontend_id = _require_supported_frontend(frontend_by_object[object_id])
        # Parse/check now, before metadata is admitted.  There is no catch-and-try-
        # legacy path here: native identity makes native admission mandatory.
        check_native_kernel(_native_source(payload))
        records.append(
            FrontendObjectRecordV1(
                object_id=object_id,
                artifact_digest=hashlib.sha256(payload).digest(),
                frontend_id=frontend_id,
            )
        )

    body = bytearray(
        _HEADER.pack(
            FRONTEND_GRAPH_MAGIC_V1,
            FRONTEND_GRAPH_VERSION_V1,
            project,
            root,
            len(records),
        )
    )
    for record in records:
        body.extend(_OBJECT.pack(record.object_id, record.artifact_digest, record.frontend_id))
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("authenticated frontend graph exceeds sealed graph byte budget")
    return bytes(body)


def decode_authenticated_frontend_graph(
    project: ObjectSpaceProject,
) -> tuple[FrontendObjectRecordV1, ...]:
    """Validate frontend identity against sealed k0 authority and opened objects."""

    if not isinstance(project, ObjectSpaceProject):
        _fail("frontend graph requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if (
        not isinstance(payload, bytes)
        or len(payload) < _HEADER.size
        or len(payload) > MAX_GRAPH_SECRET_BYTES
    ):
        _fail("authenticated frontend graph length is invalid")

    magic, version, project_id, root_id, object_count = _HEADER.unpack_from(payload, 0)
    if magic != FRONTEND_GRAPH_MAGIC_V1 or version != FRONTEND_GRAPH_VERSION_V1:
        _fail("authenticated frontend graph schema is invalid")
    if project_id != project.project_id:
        _fail("authenticated frontend graph belongs to another project")
    if root_id != project.root_object_id:
        _fail("authenticated frontend graph root identity mismatch")
    if object_count != 1:
        _fail("native frontend v1 requires exactly one authoritative object")
    expected_size = _HEADER.size + object_count * _OBJECT.size
    if len(payload) != expected_size:
        _fail("authenticated frontend graph count/length relation is non-canonical")

    offset = _HEADER.size
    records: list[FrontendObjectRecordV1] = []
    seen: set[bytes] = set()
    for _ in range(object_count):
        object_id, artifact_digest, frontend_id = _OBJECT.unpack_from(payload, offset)
        offset += _OBJECT.size
        object_id = _exact_bytes(object_id, _ID_BYTES, "sealed frontend object id")
        artifact_digest = _exact_bytes(
            artifact_digest,
            _DIGEST_BYTES,
            "sealed frontend object digest",
            nonzero=False,
        )
        frontend_id = _require_supported_frontend(frontend_id)
        if object_id in seen:
            _fail("authenticated frontend graph contains duplicate object identity")
        seen.add(object_id)
        records.append(FrontendObjectRecordV1(object_id, artifact_digest, frontend_id))

    if records != sorted(records, key=lambda record: record.object_id):
        _fail("authenticated frontend object table is not canonical")
    if records[0].object_id != root_id:
        _fail("native frontend v1 object must be the authenticated root")

    k0_by_id = {record.object_id: record for record in project.records}
    if set(k0_by_id) != seen:
        _fail("authenticated frontend object set differs from sealed k0 authority")
    if set(project.object_payloads) != seen:
        _fail("opened Object Space payload set differs from frontend authority")

    for record in records:
        k0_record = k0_by_id[record.object_id]
        if record.artifact_digest != k0_record.artifact_digest:
            _fail("authenticated frontend digest differs from sealed k0 authority")
        payload_bytes = project.object_payloads[record.object_id]
        if not isinstance(payload_bytes, bytes):
            _fail("opened frontend object payload is not bytes")
        if hashlib.sha256(payload_bytes).digest() != record.artifact_digest:
            _fail("opened frontend object digest differs from authenticated authority")
    return tuple(records)


def load_authenticated_native_kernel(project: ObjectSpaceProject) -> NativeKernelCheck:
    records = decode_authenticated_frontend_graph(project)
    record = records[0]
    if record.frontend_id != NATIVE_WITNESS_FRONTEND_V1:
        _fail("authenticated object is not bound to native witness frontend v1")
    # No parser fallback.  Native metadata commits this object to native admission.
    return check_native_kernel(_native_source(project.object_payloads[record.object_id]))


def load_authenticated_frontend_module_graph(project: ObjectSpaceProject) -> ModuleGraph:
    checked = load_authenticated_native_kernel(project)
    object_id = project.root_object_id
    key = object_id.hex()
    module = Module(
        name="<native-object>",
        path=Path("<koschei-native-object>"),
        program=checked.lowered,
        imports={},
    )
    return ModuleGraph(root=key, modules={key: module})


def check_authenticated_frontend_graph(project: ObjectSpaceProject):
    graph = load_authenticated_frontend_module_graph(project)
    report = check_graph(graph)
    return graph, report


def check_object_space_graph_by_authenticated_frontend(project: ObjectSpaceProject):
    """Dispatch only on authenticated graph schema, never source appearance."""

    if is_authenticated_frontend_graph_secret(project.graph_secret):
        return check_authenticated_frontend_graph(project)
    return _legacy_check_object_space_graph(project)
