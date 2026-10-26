"""Authenticated Object Space binding for Koschei native decision reality v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping

from .modules import Module, ModuleGraph, check_graph
from .native_decision_realities_v1 import (
    NativeDecisionRealityCheck,
    check_native_decision_reality,
)
from .object_space_v1 import MAX_GRAPH_SECRET_BYTES, ObjectSpaceError, ObjectSpaceProject


DECISION_GRAPH_MAGIC_V1 = b"KOSCHEI_OSDECIS1"
DECISION_GRAPH_VERSION_V1 = 1
_DECISION_FRONTEND_CONTEXT = b"koschei.frontend/native-decision-realities/v1"
NATIVE_DECISION_FRONTEND_V1 = hashlib.sha256(_DECISION_FRONTEND_CONTEXT).digest()

_ID_BYTES = 16
_DIGEST_BYTES = 32
_FRONTEND_BYTES = 32
_HEADER = struct.Struct(">16sB7x16s16s32s32s")


class ObjectSpaceDecisionRealityError(ObjectSpaceError):
    pass


@dataclass(frozen=True, slots=True)
class DecisionObjectRecordV1:
    object_id: bytes
    artifact_digest: bytes
    frontend_id: bytes


def _fail(message: str) -> None:
    raise ObjectSpaceDecisionRealityError(message)


def _exact(value: object, size: int, label: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or (nonzero and not any(value)):
        suffix = " non-zero" if nonzero else ""
        _fail(f"{label} must be exactly {size}{suffix} bytes")
    return value


def _source(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        _fail("native decision payload must be bytes")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ObjectSpaceDecisionRealityError("native decision payload is not valid UTF-8") from error


def is_native_decision_graph_secret(payload: object) -> bool:
    return isinstance(payload, bytes) and payload.startswith(DECISION_GRAPH_MAGIC_V1)


def encode_native_decision_graph_secret(
    *,
    project_id: bytes,
    root_object_id: bytes,
    objects: Mapping[bytes, bytes],
) -> bytes:
    project = _exact(project_id, _ID_BYTES, "project id")
    root = _exact(root_object_id, _ID_BYTES, "root object id")
    if not isinstance(objects, Mapping) or set(objects) != {root}:
        _fail("native decision v1 requires exactly one authoritative root object")
    payload = objects[root]
    check_native_decision_reality(_source(payload))
    digest = hashlib.sha256(payload).digest()
    body = _HEADER.pack(
        DECISION_GRAPH_MAGIC_V1,
        DECISION_GRAPH_VERSION_V1,
        project,
        root,
        digest,
        NATIVE_DECISION_FRONTEND_V1,
    )
    if len(body) > MAX_GRAPH_SECRET_BYTES:
        _fail("native decision graph exceeds sealed graph byte budget")
    return body


def decode_native_decision_graph(project: ObjectSpaceProject) -> DecisionObjectRecordV1:
    if not isinstance(project, ObjectSpaceProject):
        _fail("native decision graph requires a canonical ObjectSpaceProject")
    payload = project.graph_secret
    if not isinstance(payload, bytes) or len(payload) != _HEADER.size:
        _fail("native decision graph length is non-canonical")
    magic, version, project_id, root_id, digest, frontend = _HEADER.unpack(payload)
    if magic != DECISION_GRAPH_MAGIC_V1 or version != DECISION_GRAPH_VERSION_V1:
        _fail("native decision graph schema is invalid")
    if project_id != project.project_id:
        _fail("native decision graph belongs to another project")
    if root_id != project.root_object_id:
        _fail("native decision root identity mismatch")
    if frontend != NATIVE_DECISION_FRONTEND_V1:
        _fail("native decision frontend identity mismatch")
    if len(project.records) != 1 or project.records[0].object_id != root_id:
        _fail("native decision object set differs from sealed k0 authority")
    if set(project.object_payloads) != {root_id}:
        _fail("opened native decision payload set differs from authority")
    if project.records[0].artifact_digest != digest:
        _fail("native decision digest differs from sealed k0 authority")
    opened = project.object_payloads[root_id]
    if hashlib.sha256(opened).digest() != digest:
        _fail("opened native decision digest differs from authenticated authority")
    return DecisionObjectRecordV1(root_id, digest, frontend)


def load_authenticated_native_decision(project: ObjectSpaceProject) -> NativeDecisionRealityCheck:
    record = decode_native_decision_graph(project)
    return check_native_decision_reality(_source(project.object_payloads[record.object_id]))


def check_native_decision_object_space(project: ObjectSpaceProject):
    checked = load_authenticated_native_decision(project)
    key = project.root_object_id.hex()
    graph = ModuleGraph(
        root=key,
        modules={
            key: Module(
                name="<native-decision-object>",
                path=Path("<koschei-native-decision-object>"),
                program=checked.lowered,
                imports={},
            )
        },
    )
    report = check_graph(graph)
    return graph, report
