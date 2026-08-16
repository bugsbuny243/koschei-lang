"""Koschei-native sealed collection reality v1.

Collections are bounded, homogeneous native realities. V1 deliberately exposes no
index, random access, mutation, append, pop, iterator, or host container protocol.
A sealed contract authenticates the domain, cardinality and resource ceilings;
consumers may only apply closed aggregate projections defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import unicodedata
from typing import Iterable

from .native_relationship_v1 import MAX_ABS_INT64
from .native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, NativeValue


MAX_COLLECTION_ITEMS_V1 = 4096
MAX_COLLECTION_GLYPHS_BYTES_V1 = 1 << 20
MAX_COLLECTION_TOTAL_BYTES_V1 = 1 << 22
_DOMAINS = frozenset({WHOLE, TRUTH, GLYPHS})
_SEAL_CONTEXT = b"koschei.native-sealed-collection-reality/v1\x00"


class NativeSealedCollectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SealedCollectionContractV1:
    project_id: bytes
    collection_id: bytes
    domain: str
    min_count: int
    max_count: int
    issued_epoch: int
    expires_epoch: int
    max_abs_whole: int = MAX_ABS_INT64
    max_glyph_bytes: int = 1 << 16
    max_total_bytes: int = MAX_COLLECTION_TOTAL_BYTES_V1
    authority_ceiling: int = 0
    effect_ceiling: int = 0


@dataclass(frozen=True, slots=True)
class SealedCollectionDescriptorV1:
    canonical_contract: bytes
    tag: bytes


@dataclass(frozen=True, slots=True)
class NativeCollectionRealityV1:
    collection_id: bytes
    domain: str
    count: int
    digest: bytes
    _values: tuple[NativeValue, ...]


@dataclass(frozen=True, slots=True)
class CollectionProjectionV1:
    collection_id: bytes
    value: NativeValue


def _fail(message: str) -> None:
    raise NativeSealedCollectionError(message)


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


def _key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32 or len(value) > 64:
        _fail("collection seal key must contain 32..64 bytes")
    return value


def _normalize_contract(contract: SealedCollectionContractV1) -> SealedCollectionContractV1:
    if not isinstance(contract, SealedCollectionContractV1):
        _fail("collection contract has invalid type")
    project = _id(contract.project_id, "project id")
    collection = _id(contract.collection_id, "collection id")
    if contract.domain not in _DOMAINS:
        _fail("collection domain is invalid")
    if type(contract.min_count) is not int or type(contract.max_count) is not int:
        _fail("collection count ceilings must be integers")
    if contract.min_count < 0 or contract.max_count < contract.min_count or contract.max_count > MAX_COLLECTION_ITEMS_V1:
        _fail("collection cardinality is outside v1 range")
    issued = _epoch(contract.issued_epoch, "issued epoch")
    expires = _epoch(contract.expires_epoch, "expiry epoch")
    if issued > expires:
        _fail("collection expiry precedes issue epoch")
    whole = _u64(contract.max_abs_whole, "collection whole ceiling")
    glyphs = _u64(contract.max_glyph_bytes, "collection glyph ceiling")
    total = _u64(contract.max_total_bytes, "collection total byte ceiling")
    if whole > MAX_ABS_INT64:
        _fail("collection whole ceiling exceeds native Int64 range")
    if glyphs == 0 or glyphs > MAX_COLLECTION_GLYPHS_BYTES_V1:
        _fail("collection glyph ceiling is outside v1 range")
    if total == 0 or total > MAX_COLLECTION_TOTAL_BYTES_V1:
        _fail("collection total byte ceiling is outside v1 range")
    authority = _u64(contract.authority_ceiling, "collection authority ceiling")
    effects = _u64(contract.effect_ceiling, "collection effect ceiling")
    if authority or effects:
        _fail("collection reality v1 admits only zero authority and zero effects")
    return SealedCollectionContractV1(
        project,
        collection,
        contract.domain,
        contract.min_count,
        contract.max_count,
        issued,
        expires,
        whole,
        glyphs,
        total,
        authority,
        effects,
    )


def _contract_bytes(contract: SealedCollectionContractV1) -> bytes:
    contract = _normalize_contract(contract)
    body = {
        "v": 1,
        "project": contract.project_id.hex(),
        "collection": contract.collection_id.hex(),
        "domain": contract.domain,
        "min": contract.min_count,
        "max": contract.max_count,
        "issued": contract.issued_epoch,
        "expires": contract.expires_epoch,
        "max_abs_whole": contract.max_abs_whole,
        "max_glyph_bytes": contract.max_glyph_bytes,
        "max_total_bytes": contract.max_total_bytes,
        "authority": contract.authority_ceiling,
        "effects": contract.effect_ceiling,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def seal_collection_contract_v1(contract: SealedCollectionContractV1, key: bytes) -> SealedCollectionDescriptorV1:
    canonical = _contract_bytes(contract)
    tag = hmac.new(_key(key), _SEAL_CONTEXT + canonical, hashlib.sha256).digest()
    return SealedCollectionDescriptorV1(canonical, tag)


def _load_contract(sealed: SealedCollectionDescriptorV1, key: bytes) -> SealedCollectionContractV1:
    if not isinstance(sealed, SealedCollectionDescriptorV1):
        _fail("collection descriptor has invalid type")
    if not isinstance(sealed.canonical_contract, bytes) or not isinstance(sealed.tag, bytes) or len(sealed.tag) != 32:
        _fail("collection descriptor is malformed")
    expected = hmac.new(_key(key), _SEAL_CONTEXT + sealed.canonical_contract, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sealed.tag):
        _fail("collection descriptor authentication failed")
    try:
        body = json.loads(sealed.canonical_contract.decode("utf-8"))
        if set(body) != {"v", "project", "collection", "domain", "min", "max", "issued", "expires", "max_abs_whole", "max_glyph_bytes", "max_total_bytes", "authority", "effects"} or body["v"] != 1:
            _fail("collection contract schema is invalid")
        contract = SealedCollectionContractV1(
            bytes.fromhex(body["project"]),
            bytes.fromhex(body["collection"]),
            body["domain"],
            body["min"],
            body["max"],
            body["issued"],
            body["expires"],
            body["max_abs_whole"],
            body["max_glyph_bytes"],
            body["max_total_bytes"],
            body["authority"],
            body["effects"],
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeSealedCollectionError("collection contract encoding is invalid") from error
    if _contract_bytes(contract) != sealed.canonical_contract:
        _fail("collection contract is not canonical")
    return _normalize_contract(contract)


def _admit_scalar(contract: SealedCollectionContractV1, raw: object) -> NativeValue:
    if contract.domain == WHOLE:
        if type(raw) is not int:
            _fail("collection whole item requires an integer without coercion")
        if raw < -MAX_ABS_INT64 or raw > MAX_ABS_INT64 or abs(raw) > contract.max_abs_whole:
            _fail("collection whole item exceeds sealed absolute-value ceiling")
        return NativeValue(WHOLE, raw)
    if contract.domain == TRUTH:
        if type(raw) is not bool:
            _fail("collection truth item requires a boolean without coercion")
        return NativeValue(TRUTH, raw)
    if contract.domain == GLYPHS:
        if not isinstance(raw, str):
            _fail("collection glyphs item requires text without coercion")
        if raw != unicodedata.normalize("NFC", raw):
            _fail("collection glyphs item must be Unicode NFC canonical")
        encoded = raw.encode("utf-8")
        if len(encoded) > contract.max_glyph_bytes:
            _fail("collection glyphs item exceeds sealed byte ceiling")
        if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in raw):
            _fail("collection glyphs item contains forbidden control characters")
        return NativeValue(GLYPHS, raw)
    _fail("collection contract uses unsupported domain")


def _digest_values(collection_id: bytes, values: tuple[NativeValue, ...]) -> bytes:
    hasher = hashlib.sha256()
    hasher.update(b"koschei.native-collection-values/v1\x00")
    hasher.update(collection_id)
    for value in values:
        hasher.update(value.domain.encode("ascii") + b"\x00")
        if value.domain == WHOLE:
            payload = str(value.value).encode("ascii")
        elif value.domain == TRUTH:
            payload = b"1" if value.value else b"0"
        else:
            payload = str(value.value).encode("utf-8")
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    return hasher.digest()


def admit_collection_reality_v1(
    sealed: SealedCollectionDescriptorV1,
    key: bytes,
    *,
    current_epoch: int,
    items: Iterable[object],
) -> NativeCollectionRealityV1:
    contract = _load_contract(sealed, key)
    epoch = _epoch(current_epoch, "current Object Space epoch")
    if epoch < contract.issued_epoch or epoch > contract.expires_epoch:
        _fail("collection contract is stale or not yet valid")
    if isinstance(items, (str, bytes, bytearray, dict)):
        _fail("collection admission requires a bounded item stream, not ambient container text/mapping")
    try:
        raw_items = tuple(items)
    except TypeError as error:
        raise NativeSealedCollectionError("collection admission requires an iterable item stream") from error
    count = len(raw_items)
    if count < contract.min_count or count > contract.max_count:
        _fail("collection item count violates sealed cardinality")
    values = tuple(_admit_scalar(contract, item) for item in raw_items)
    total_bytes = 0
    for value in values:
        if value.domain == WHOLE:
            total_bytes += 8
        elif value.domain == TRUTH:
            total_bytes += 1
        else:
            total_bytes += len(str(value.value).encode("utf-8"))
    if total_bytes > contract.max_total_bytes:
        _fail("collection reality exceeds sealed total byte ceiling")
    return NativeCollectionRealityV1(
        contract.collection_id,
        contract.domain,
        count,
        _digest_values(contract.collection_id, values),
        values,
    )


def project_collection_count_v1(reality: NativeCollectionRealityV1) -> CollectionProjectionV1:
    if not isinstance(reality, NativeCollectionRealityV1):
        _fail("collection reality has invalid type")
    return CollectionProjectionV1(reality.collection_id, NativeValue(WHOLE, reality.count))


def project_collection_sum_v1(reality: NativeCollectionRealityV1) -> CollectionProjectionV1:
    if not isinstance(reality, NativeCollectionRealityV1) or reality.domain != WHOLE:
        _fail("sum projection requires a sealed whole collection")
    total = 0
    for value in reality._values:
        total += int(value.value)
        if total < -MAX_ABS_INT64 or total > MAX_ABS_INT64:
            _fail("collection sum exceeds native Int64 range")
    return CollectionProjectionV1(reality.collection_id, NativeValue(WHOLE, total))


def project_collection_all_v1(reality: NativeCollectionRealityV1) -> CollectionProjectionV1:
    if not isinstance(reality, NativeCollectionRealityV1) or reality.domain != TRUTH:
        _fail("all projection requires a sealed truth collection")
    return CollectionProjectionV1(reality.collection_id, NativeValue(TRUTH, all(bool(v.value) for v in reality._values)))


def project_collection_any_v1(reality: NativeCollectionRealityV1) -> CollectionProjectionV1:
    if not isinstance(reality, NativeCollectionRealityV1) or reality.domain != TRUTH:
        _fail("any projection requires a sealed truth collection")
    return CollectionProjectionV1(reality.collection_id, NativeValue(TRUTH, any(bool(v.value) for v in reality._values)))


def project_collection_merge_v1(reality: NativeCollectionRealityV1) -> CollectionProjectionV1:
    if not isinstance(reality, NativeCollectionRealityV1) or reality.domain != GLYPHS:
        _fail("merge projection requires a sealed glyphs collection")
    merged = "".join(str(v.value) for v in reality._values)
    if len(merged.encode("utf-8")) > MAX_COLLECTION_GLYPHS_BYTES_V1:
        _fail("collection merge exceeds native glyph result ceiling")
    return CollectionProjectionV1(reality.collection_id, NativeValue(GLYPHS, merged))


def collection_fingerprint_v1(sealed: SealedCollectionDescriptorV1) -> bytes:
    if not isinstance(sealed, SealedCollectionDescriptorV1) or not isinstance(sealed.canonical_contract, bytes):
        _fail("collection descriptor has invalid type")
    return hashlib.sha256(_SEAL_CONTEXT + sealed.canonical_contract).digest()
