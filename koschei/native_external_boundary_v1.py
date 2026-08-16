"""Sealed typed admission boundary for untrusted external mappings.

V1 deliberately does not expose JSON keys, HTTP parameter names, or database
column names to Koschei source. A sealed, authenticated boundary contract maps
those ambient external names to anonymous contiguous native value slots.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import unicodedata
from typing import Mapping, Sequence

from .native_relationship_v1 import MAX_ABS_INT64
from .native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, NativeValue


EXTERNAL_JSON = "json"
EXTERNAL_HTTP = "http"
EXTERNAL_DB = "db"
_EXTERNAL_KINDS = frozenset({EXTERNAL_JSON, EXTERNAL_HTTP, EXTERNAL_DB})
_DOMAINS = frozenset({WHOLE, TRUTH, GLYPHS})
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
MAX_EXTERNAL_FIELDS_V1 = 64
MAX_EXTERNAL_PAYLOAD_BYTES_V1 = 1 << 20
MAX_EXTERNAL_GLYPHS_BYTES_V1 = 1 << 16
_SEAL_CONTEXT = b"koschei.native-external-boundary/v1\x00"


class NativeExternalBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalFieldRuleV1:
    slot: int
    external_name: str
    domain: str
    max_abs_whole: int = MAX_ABS_INT64
    max_glyph_bytes: int = MAX_EXTERNAL_GLYPHS_BYTES_V1


@dataclass(frozen=True, slots=True)
class ExternalBoundaryContractV1:
    project_id: bytes
    boundary_id: bytes
    source_kind: str
    fields: tuple[ExternalFieldRuleV1, ...]
    issued_epoch: int
    expires_epoch: int
    max_payload_bytes: int = MAX_EXTERNAL_PAYLOAD_BYTES_V1
    authority_ceiling: int = 0
    effect_ceiling: int = 0


@dataclass(frozen=True, slots=True)
class SealedExternalBoundaryV1:
    canonical_contract: bytes
    tag: bytes


@dataclass(frozen=True, slots=True)
class ExternalAdmissionV1:
    boundary_id: bytes
    values: tuple[NativeValue, ...]


def _fail(message: str) -> None:
    raise NativeExternalBoundaryError(message)


def _id(value: object, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != 16 or not any(value):
        _fail(f"{label} must be exactly 16 non-zero bytes")
    return value


def _epoch(value: object, label: str) -> int:
    if type(value) is not int or value <= 0 or value > (1 << 63) - 1:
        _fail(f"{label} must be a positive bounded integer")
    return value


def _u64(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > (1 << 64) - 1:
        _fail(f"{label} must be an unsigned 64-bit integer")
    return value


def _canonical_name(value: object) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        _fail("external field name is not canonical v1 text")
    if value != unicodedata.normalize("NFC", value):
        _fail("external field name must be Unicode NFC canonical")
    return value


def _normalize_contract(contract: ExternalBoundaryContractV1) -> ExternalBoundaryContractV1:
    if not isinstance(contract, ExternalBoundaryContractV1):
        _fail("external boundary contract has invalid type")
    project_id = _id(contract.project_id, "project id")
    boundary_id = _id(contract.boundary_id, "boundary id")
    if contract.source_kind not in _EXTERNAL_KINDS:
        _fail("external source kind is invalid")
    issued = _epoch(contract.issued_epoch, "issued epoch")
    expires = _epoch(contract.expires_epoch, "expiry epoch")
    if issued > expires:
        _fail("external boundary expiry precedes issue epoch")
    max_payload = _u64(contract.max_payload_bytes, "external payload ceiling")
    if max_payload == 0 or max_payload > MAX_EXTERNAL_PAYLOAD_BYTES_V1:
        _fail("external payload ceiling is outside v1 range")
    authority = _u64(contract.authority_ceiling, "external authority ceiling")
    effects = _u64(contract.effect_ceiling, "external effect ceiling")
    if authority or effects:
        _fail("external boundary v1 admits only zero authority and zero effects")
    fields = tuple(contract.fields)
    if not fields or len(fields) > MAX_EXTERNAL_FIELDS_V1:
        _fail("external boundary field count is outside v1 range")
    names: set[str] = set()
    slots: set[int] = set()
    normalized: list[ExternalFieldRuleV1] = []
    for field in fields:
        if not isinstance(field, ExternalFieldRuleV1):
            _fail("external field rule has invalid type")
        if type(field.slot) is not int or field.slot < 0 or field.slot >= MAX_EXTERNAL_FIELDS_V1:
            _fail("external field slot is outside v1 range")
        name = _canonical_name(field.external_name)
        if name in names or field.slot in slots:
            _fail("external field names and slots must be unique")
        if field.domain not in _DOMAINS:
            _fail("external field domain is invalid")
        whole = _u64(field.max_abs_whole, "external whole ceiling")
        glyphs = _u64(field.max_glyph_bytes, "external glyph ceiling")
        if whole > MAX_ABS_INT64:
            _fail("external whole ceiling exceeds native Int64 range")
        if glyphs == 0 or glyphs > MAX_EXTERNAL_GLYPHS_BYTES_V1:
            _fail("external glyph ceiling is outside v1 range")
        names.add(name)
        slots.add(field.slot)
        normalized.append(ExternalFieldRuleV1(field.slot, name, field.domain, whole, glyphs))
    normalized.sort(key=lambda item: item.slot)
    if tuple(item.slot for item in normalized) != tuple(range(len(normalized))):
        _fail("external field slots must be contiguous from zero")
    return ExternalBoundaryContractV1(
        project_id,
        boundary_id,
        contract.source_kind,
        tuple(normalized),
        issued,
        expires,
        max_payload,
        authority,
        effects,
    )


def _contract_bytes(contract: ExternalBoundaryContractV1) -> bytes:
    contract = _normalize_contract(contract)
    body = {
        "v": 1,
        "project": contract.project_id.hex(),
        "boundary": contract.boundary_id.hex(),
        "kind": contract.source_kind,
        "issued": contract.issued_epoch,
        "expires": contract.expires_epoch,
        "max_payload": contract.max_payload_bytes,
        "authority": contract.authority_ceiling,
        "effects": contract.effect_ceiling,
        "fields": [
            {
                "slot": field.slot,
                "name": field.external_name,
                "domain": field.domain,
                "max_abs_whole": field.max_abs_whole,
                "max_glyph_bytes": field.max_glyph_bytes,
            }
            for field in contract.fields
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _key(key: object) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32 or len(key) > 64:
        _fail("external boundary seal key must contain 32..64 bytes")
    return key


def seal_external_boundary_v1(contract: ExternalBoundaryContractV1, key: bytes) -> SealedExternalBoundaryV1:
    canonical = _contract_bytes(contract)
    tag = hmac.new(_key(key), _SEAL_CONTEXT + canonical, hashlib.sha256).digest()
    return SealedExternalBoundaryV1(canonical, tag)


def _load_contract(sealed: SealedExternalBoundaryV1, key: bytes) -> ExternalBoundaryContractV1:
    if not isinstance(sealed, SealedExternalBoundaryV1):
        _fail("external boundary seal has invalid type")
    if not isinstance(sealed.canonical_contract, bytes) or not isinstance(sealed.tag, bytes) or len(sealed.tag) != 32:
        _fail("external boundary seal is malformed")
    expected = hmac.new(_key(key), _SEAL_CONTEXT + sealed.canonical_contract, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sealed.tag):
        _fail("external boundary seal authentication failed")
    try:
        body = json.loads(sealed.canonical_contract.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeExternalBoundaryError("external boundary contract encoding is invalid") from error
    try:
        if set(body) != {"v", "project", "boundary", "kind", "issued", "expires", "max_payload", "authority", "effects", "fields"} or body["v"] != 1:
            _fail("external boundary contract schema is invalid")
        fields = tuple(
            ExternalFieldRuleV1(
                item["slot"], item["name"], item["domain"], item["max_abs_whole"], item["max_glyph_bytes"]
            )
            for item in body["fields"]
        )
        contract = ExternalBoundaryContractV1(
            bytes.fromhex(body["project"]),
            bytes.fromhex(body["boundary"]),
            body["kind"],
            fields,
            body["issued"],
            body["expires"],
            body["max_payload"],
            body["authority"],
            body["effects"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise NativeExternalBoundaryError("external boundary contract fields are invalid") from error
    if _contract_bytes(contract) != sealed.canonical_contract:
        _fail("external boundary contract is not canonical")
    return _normalize_contract(contract)


def _payload_size(payload: Mapping[str, object]) -> int:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise NativeExternalBoundaryError("external mapping is not canonical JSON-compatible data") from error
    return len(encoded)


def _admit_value(field: ExternalFieldRuleV1, raw: object) -> NativeValue:
    if field.domain == WHOLE:
        if type(raw) is not int:
            _fail("external whole value requires an integer without coercion")
        if raw < -MAX_ABS_INT64 or raw > MAX_ABS_INT64 or abs(raw) > field.max_abs_whole:
            _fail("external whole value exceeds sealed absolute-value ceiling")
        return NativeValue(WHOLE, raw)
    if field.domain == TRUTH:
        if type(raw) is not bool:
            _fail("external truth value requires a boolean without coercion")
        return NativeValue(TRUTH, raw)
    if field.domain == GLYPHS:
        if not isinstance(raw, str):
            _fail("external glyphs value requires text without coercion")
        if raw != unicodedata.normalize("NFC", raw):
            _fail("external glyphs value must be Unicode NFC canonical")
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as error:
            raise NativeExternalBoundaryError("external glyphs value is not valid UTF-8") from error
        if len(encoded) > field.max_glyph_bytes:
            _fail("external glyphs value exceeds sealed byte ceiling")
        if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in raw):
            _fail("external glyphs value contains forbidden control characters")
        return NativeValue(GLYPHS, raw)
    _fail("external field uses unsupported scalar domain")


def admit_external_mapping_v1(
    sealed: SealedExternalBoundaryV1,
    key: bytes,
    *,
    current_epoch: int,
    source_kind: str,
    payload: Mapping[str, object],
) -> ExternalAdmissionV1:
    contract = _load_contract(sealed, key)
    epoch = _epoch(current_epoch, "current Object Space epoch")
    if epoch < contract.issued_epoch or epoch > contract.expires_epoch:
        _fail("external boundary contract is stale or not yet valid")
    if source_kind != contract.source_kind:
        _fail("external source kind does not match sealed boundary")
    if not isinstance(payload, Mapping):
        _fail("external payload must be a mapping")
    expected_names = tuple(field.external_name for field in contract.fields)
    if set(payload) != set(expected_names) or len(payload) != len(expected_names):
        _fail("external payload keys must exactly match sealed field set")
    if any(not isinstance(name, str) or name != unicodedata.normalize("NFC", name) for name in payload):
        _fail("external payload contains non-canonical key text")
    if _payload_size(payload) > contract.max_payload_bytes:
        _fail("external payload exceeds sealed byte ceiling")
    values = tuple(_admit_value(field, payload[field.external_name]) for field in contract.fields)
    return ExternalAdmissionV1(contract.boundary_id, values)


def contract_fingerprint_v1(sealed: SealedExternalBoundaryV1) -> bytes:
    if not isinstance(sealed, SealedExternalBoundaryV1) or not isinstance(sealed.canonical_contract, bytes):
        _fail("external boundary seal has invalid type")
    return hashlib.sha256(_SEAL_CONTEXT + sealed.canonical_contract).digest()
