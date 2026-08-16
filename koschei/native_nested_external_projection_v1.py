"""Sealed nested external projection for untrusted JSON-like payloads.

V1 admits only an exact, authenticated tree shape. External path names remain
boundary metadata and are projected into anonymous native slots before reusable
Koschei logic sees values.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import unicodedata
from typing import Mapping, Sequence

from .native_external_boundary_v1 import (
    EXTERNAL_JSON,
    ExternalAdmissionV1,
    ExternalFieldRuleV1,
    NativeExternalBoundaryError,
    _admit_value,
    _epoch,
    _id,
    _key,
    _u64,
)
from .native_value_domains_v1 import NativeValue


MAX_NESTED_DEPTH_V1 = 8
MAX_NESTED_LEAVES_V1 = 64
MAX_NESTED_KEY_BYTES_V1 = 128
MAX_NESTED_PAYLOAD_BYTES_V1 = 1 << 20
_SEAL_CONTEXT = b"koschei.native-nested-external-projection/v1\x00"


class NativeNestedExternalProjectionError(NativeExternalBoundaryError):
    pass


@dataclass(frozen=True, slots=True)
class NestedProjectionRuleV1:
    slot: int
    path: tuple[str, ...]
    domain: str
    max_abs_whole: int = (1 << 63) - 1
    max_glyph_bytes: int = 1 << 16


@dataclass(frozen=True, slots=True)
class NestedProjectionContractV1:
    project_id: bytes
    boundary_id: bytes
    rules: tuple[NestedProjectionRuleV1, ...]
    issued_epoch: int
    expires_epoch: int
    max_payload_bytes: int = MAX_NESTED_PAYLOAD_BYTES_V1
    authority_ceiling: int = 0
    effect_ceiling: int = 0


@dataclass(frozen=True, slots=True)
class SealedNestedProjectionV1:
    canonical_contract: bytes
    tag: bytes


@dataclass(frozen=True, slots=True)
class NestedProjectionAdmissionV1:
    boundary_id: bytes
    values: tuple[NativeValue, ...]


def _fail(message: str) -> None:
    raise NativeNestedExternalProjectionError(message)


def _segment(value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail("nested external path segment must be non-empty text")
    if value != unicodedata.normalize("NFC", value):
        _fail("nested external path segment must be Unicode NFC canonical")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise NativeNestedExternalProjectionError("nested external path segment is not valid UTF-8") from error
    if len(encoded) > MAX_NESTED_KEY_BYTES_V1:
        _fail("nested external path segment exceeds v1 byte ceiling")
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in value):
        _fail("nested external path segment contains forbidden control characters")
    if value in {".", ".."}:
        _fail("nested external path segment is reserved")
    return value


def _normalize_contract(contract: NestedProjectionContractV1) -> NestedProjectionContractV1:
    if not isinstance(contract, NestedProjectionContractV1):
        _fail("nested projection contract has invalid type")
    project = _id(contract.project_id, "project id")
    boundary = _id(contract.boundary_id, "boundary id")
    issued = _epoch(contract.issued_epoch, "issued epoch")
    expires = _epoch(contract.expires_epoch, "expiry epoch")
    if issued > expires:
        _fail("nested projection expiry precedes issue epoch")
    max_payload = _u64(contract.max_payload_bytes, "nested payload ceiling")
    if max_payload == 0 or max_payload > MAX_NESTED_PAYLOAD_BYTES_V1:
        _fail("nested payload ceiling is outside v1 range")
    authority = _u64(contract.authority_ceiling, "nested authority ceiling")
    effects = _u64(contract.effect_ceiling, "nested effect ceiling")
    if authority or effects:
        _fail("nested projection v1 admits only zero authority and zero effects")
    rules = tuple(contract.rules)
    if not rules or len(rules) > MAX_NESTED_LEAVES_V1:
        _fail("nested projection leaf count is outside v1 range")
    slots: set[int] = set()
    paths: set[tuple[str, ...]] = set()
    normalized: list[NestedProjectionRuleV1] = []
    for rule in rules:
        if not isinstance(rule, NestedProjectionRuleV1):
            _fail("nested projection rule has invalid type")
        if type(rule.slot) is not int or rule.slot < 0 or rule.slot >= MAX_NESTED_LEAVES_V1:
            _fail("nested projection slot is outside v1 range")
        path = tuple(_segment(item) for item in rule.path)
        if not path or len(path) > MAX_NESTED_DEPTH_V1:
            _fail("nested projection path depth is outside v1 range")
        if rule.slot in slots or path in paths:
            _fail("nested projection slots and paths must be unique")
        field = ExternalFieldRuleV1(rule.slot, "leaf", rule.domain, rule.max_abs_whole, rule.max_glyph_bytes)
        # Reuse #207's scalar/domain ceiling validator without exposing the real path name.
        _admit_value(field, 0 if rule.domain == "whole" else False if rule.domain == "truth" else "")
        slots.add(rule.slot)
        paths.add(path)
        normalized.append(NestedProjectionRuleV1(rule.slot, path, rule.domain, rule.max_abs_whole, rule.max_glyph_bytes))
    normalized.sort(key=lambda item: item.slot)
    if tuple(item.slot for item in normalized) != tuple(range(len(normalized))):
        _fail("nested projection slots must be contiguous from zero")
    for left in paths:
        for right in paths:
            if left != right and len(left) < len(right) and right[: len(left)] == left:
                _fail("nested projection cannot seal a path as both leaf and branch")
    return NestedProjectionContractV1(project, boundary, tuple(normalized), issued, expires, max_payload, authority, effects)


def _contract_bytes(contract: NestedProjectionContractV1) -> bytes:
    contract = _normalize_contract(contract)
    body = {
        "v": 1,
        "project": contract.project_id.hex(),
        "boundary": contract.boundary_id.hex(),
        "kind": EXTERNAL_JSON,
        "issued": contract.issued_epoch,
        "expires": contract.expires_epoch,
        "max_payload": contract.max_payload_bytes,
        "authority": contract.authority_ceiling,
        "effects": contract.effect_ceiling,
        "rules": [
            {
                "slot": rule.slot,
                "path": list(rule.path),
                "domain": rule.domain,
                "max_abs_whole": rule.max_abs_whole,
                "max_glyph_bytes": rule.max_glyph_bytes,
            }
            for rule in contract.rules
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def seal_nested_projection_v1(contract: NestedProjectionContractV1, key: bytes) -> SealedNestedProjectionV1:
    canonical = _contract_bytes(contract)
    tag = hmac.new(_key(key), _SEAL_CONTEXT + canonical, hashlib.sha256).digest()
    return SealedNestedProjectionV1(canonical, tag)


def _load_contract(sealed: SealedNestedProjectionV1, key: bytes) -> NestedProjectionContractV1:
    if not isinstance(sealed, SealedNestedProjectionV1):
        _fail("nested projection seal has invalid type")
    if not isinstance(sealed.canonical_contract, bytes) or not isinstance(sealed.tag, bytes) or len(sealed.tag) != 32:
        _fail("nested projection seal is malformed")
    expected = hmac.new(_key(key), _SEAL_CONTEXT + sealed.canonical_contract, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sealed.tag):
        _fail("nested projection seal authentication failed")
    try:
        body = json.loads(sealed.canonical_contract.decode("utf-8"))
        if set(body) != {"v", "project", "boundary", "kind", "issued", "expires", "max_payload", "authority", "effects", "rules"}:
            _fail("nested projection contract schema is invalid")
        if body["v"] != 1 or body["kind"] != EXTERNAL_JSON:
            _fail("nested projection contract version or kind is invalid")
        rules = tuple(
            NestedProjectionRuleV1(
                item["slot"], tuple(item["path"]), item["domain"], item["max_abs_whole"], item["max_glyph_bytes"]
            )
            for item in body["rules"]
        )
        contract = NestedProjectionContractV1(
            bytes.fromhex(body["project"]), bytes.fromhex(body["boundary"]), rules,
            body["issued"], body["expires"], body["max_payload"], body["authority"], body["effects"]
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeNestedExternalProjectionError("nested projection contract encoding is invalid") from error
    if _contract_bytes(contract) != sealed.canonical_contract:
        _fail("nested projection contract is not canonical")
    return _normalize_contract(contract)


def _payload_size(payload: Mapping[str, object]) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise NativeNestedExternalProjectionError("nested external payload is not canonical JSON-compatible data") from error


def _shape_from_rules(rules: Sequence[NestedProjectionRuleV1]) -> dict[str, object]:
    root: dict[str, object] = {}
    for rule in rules:
        cursor = root
        for segment in rule.path[:-1]:
            child = cursor.setdefault(segment, {})
            if not isinstance(child, dict):
                _fail("nested projection sealed shape is ambiguous")
            cursor = child
        cursor[rule.path[-1]] = None
    return root


def _validate_exact_shape(payload: Mapping[str, object], shape: Mapping[str, object], *, depth: int = 1) -> None:
    if depth > MAX_NESTED_DEPTH_V1:
        _fail("nested external payload exceeds sealed depth")
    if not isinstance(payload, Mapping):
        _fail("nested external branch must be a mapping")
    expected = set(shape)
    if set(payload) != expected or len(payload) != len(expected):
        _fail("nested external payload shape does not exactly match sealed projection")
    for key, child_shape in shape.items():
        _segment(key)
        raw = payload[key]
        if child_shape is None:
            if isinstance(raw, Mapping):
                _fail("nested external leaf cannot be a mapping")
        else:
            _validate_exact_shape(raw, child_shape, depth=depth + 1)


def _read_path(payload: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = payload
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            _fail("nested external sealed path is missing")
        current = current[segment]
    return current


def admit_nested_external_json_v1(
    sealed: SealedNestedProjectionV1,
    key: bytes,
    *,
    current_epoch: int,
    payload: Mapping[str, object],
) -> NestedProjectionAdmissionV1:
    contract = _load_contract(sealed, key)
    epoch = _epoch(current_epoch, "current Object Space epoch")
    if epoch < contract.issued_epoch or epoch > contract.expires_epoch:
        _fail("nested projection contract is stale or not yet valid")
    if not isinstance(payload, Mapping):
        _fail("nested external payload must be a mapping")
    if _payload_size(payload) > contract.max_payload_bytes:
        _fail("nested external payload exceeds sealed byte ceiling")
    _validate_exact_shape(payload, _shape_from_rules(contract.rules))
    values: list[NativeValue] = []
    for rule in contract.rules:
        anonymous = ExternalFieldRuleV1(rule.slot, "leaf", rule.domain, rule.max_abs_whole, rule.max_glyph_bytes)
        values.append(_admit_value(anonymous, _read_path(payload, rule.path)))
    return NestedProjectionAdmissionV1(contract.boundary_id, tuple(values))


def nested_projection_fingerprint_v1(sealed: SealedNestedProjectionV1) -> bytes:
    if not isinstance(sealed, SealedNestedProjectionV1) or not isinstance(sealed.canonical_contract, bytes):
        _fail("nested projection seal has invalid type")
    return hashlib.sha256(_SEAL_CONTEXT + sealed.canonical_contract).digest()
