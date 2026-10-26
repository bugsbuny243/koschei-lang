"""Koschei Object Space v1: semantic-free canonical project storage.

Canonical filesystem surface:

    <project>/
        k0
        k1/
            <256-bit opaque locator>
            <256-bit opaque locator>
            ...

No source filename, module label, test role, dependency name, root role or file
extension is authoritative.  k0 is an externally sealed root capsule; k1 contains
externally sealed object payloads under opaque locators.  Graph/topology bytes live
inside the sealed k0 payload, not as plaintext project metadata.

The module intentionally provides no built-in encryption implementation.  Crypto
is delegated to an audited provider satisfying ``ObjectSpaceCryptoProvider``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import struct
from typing import Mapping

from .crypto_agility_v1 import (
    OBJECT_SPACE_PQ1,
    CryptoProfileV1,
    ObjectSpaceCryptoProvider,
    require_profile,
)
from .native_reality_v1 import (
    MAX_SOURCE_BYTES,
    NativeRealityError,
    _absolute_no_symlink_resolution,
    _fresh_nonzero,
    _open_directory_at,
    _open_directory_path,
    _read_regular_at,
    _require_secure_platform,
    _safe_remove_created_root,
    _unlink_at,
    _write_exclusive_at,
)
from .temporal_access_v1 import (
    TemporalAccessPolicy,
    issue_temporal_handle,
    verify_temporal_handle,
)


ROOT_CAPSULE_NAME = "k0"
OBJECT_STORE_NAME = "k1"
SPACE_SCHEMA_VERSION = 1
MAX_OBJECTS = 4096
MAX_GRAPH_SECRET_BYTES = 4 << 20
MAX_SEALED_OBJECT_BYTES = (MAX_SOURCE_BYTES * 2) + (1 << 20)
MAX_SEALED_ROOT_BYTES = 8 << 20

_PROJECT_ID_BYTES = 16
_OBJECT_ID_BYTES = 16
_LOCATOR_BYTES = 32
_DIGEST_BYTES = 32
_MAGIC = b"KOSCHEI_SPACE\x00\x00\x00"
_HEADER = struct.Struct(">16sB7x16sQ16s32sII")
_RECORD = struct.Struct(">16s32s32s")
_LOCATOR_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_PURPOSE = b"koschei.object-space.root/v1"
_OBJECT_PURPOSE = b"koschei.object-space.object/v1"


class ObjectSpaceError(NativeRealityError):
    """Raised when Object Space authority/storage fails closed."""


@dataclass(frozen=True, slots=True)
class ObjectSpaceRecord:
    object_id: bytes
    artifact_digest: bytes
    locator: bytes

    @property
    def object_id_hex(self) -> str:
        return self.object_id.hex()

    @property
    def locator_text(self) -> str:
        return self.locator.hex()


@dataclass(frozen=True, slots=True)
class ObjectSpaceProject:
    root: Path
    project_id: bytes
    epoch: int
    root_object_id: bytes
    records: tuple[ObjectSpaceRecord, ...]
    graph_secret: bytes
    object_payloads: Mapping[bytes, bytes]
    unreferenced_locators: tuple[str, ...]

    @property
    def project_id_hex(self) -> str:
        return self.project_id.hex()


def _fail(message: str) -> None:
    raise ObjectSpaceError(message)


def _bytes_exact(value: object, size: int, label: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or not any(value):
        _fail(f"{label} must be exactly {size} non-zero bytes")
    return value


def _epoch(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > (1 << 64) - 1
    ):
        _fail("object-space epoch must be a positive uint64")
    return value


def _profile_digest(profile: CryptoProfileV1) -> bytes:
    fields = (
        profile.profile_id,
        profile.at_rest_aead,
        profile.key_establishment,
        profile.primary_signature,
        profile.backup_signature,
        profile.digest,
    )
    payload = b"\x00".join(field.encode("ascii") for field in fields)
    return hashlib.sha256(payload).digest()


def _fresh_locator(excluded: set[bytes]) -> bytes:
    while True:
        locator = _fresh_nonzero(_LOCATOR_BYTES)
        if locator not in excluded:
            excluded.add(locator)
            return locator


def _canonical_objects(objects: Mapping[bytes, bytes]) -> tuple[tuple[bytes, bytes], ...]:
    if not isinstance(objects, Mapping) or not objects or len(objects) > MAX_OBJECTS:
        _fail(f"object map must contain 1..{MAX_OBJECTS} objects")
    normalized: list[tuple[bytes, bytes]] = []
    for object_id, payload in objects.items():
        identity = _bytes_exact(object_id, _OBJECT_ID_BYTES, "object id")
        if not isinstance(payload, bytes):
            _fail("object payload must be bytes")
        if len(payload) > MAX_SOURCE_BYTES:
            _fail(f"object payload exceeds {MAX_SOURCE_BYTES} bytes")
        normalized.append((identity, payload))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def _root_aad(project_id: bytes, epoch: int) -> bytes:
    return b"\x00".join((b"root", project_id, epoch.to_bytes(8, "big")))


def _object_aad(project_id: bytes, epoch: int, object_id: bytes, locator: bytes) -> bytes:
    return b"\x00".join(
        (b"object", project_id, epoch.to_bytes(8, "big"), object_id, locator)
    )


def _encode_root(
    *,
    profile: CryptoProfileV1,
    project_id: bytes,
    epoch: int,
    root_object_id: bytes,
    records: tuple[ObjectSpaceRecord, ...],
    graph_secret: bytes,
) -> bytes:
    if not isinstance(graph_secret, bytes) or len(graph_secret) > MAX_GRAPH_SECRET_BYTES:
        _fail(f"graph secret exceeds {MAX_GRAPH_SECRET_BYTES} bytes")
    if not records or len(records) > MAX_OBJECTS:
        _fail("root capsule object count is invalid")
    by_id: set[bytes] = set()
    locators: set[bytes] = set()
    for record in records:
        identity = _bytes_exact(record.object_id, _OBJECT_ID_BYTES, "object id")
        _bytes_exact(record.artifact_digest, _DIGEST_BYTES, "artifact digest")
        locator = _bytes_exact(record.locator, _LOCATOR_BYTES, "locator")
        if identity in by_id:
            _fail("duplicate object id in root capsule")
        if locator in locators:
            _fail("duplicate physical locator in root capsule")
        by_id.add(identity)
        locators.add(locator)
    root = _bytes_exact(root_object_id, _OBJECT_ID_BYTES, "root object id")
    if root not in by_id:
        _fail("root object id is absent from object records")

    body = bytearray(
        _HEADER.pack(
            _MAGIC,
            SPACE_SCHEMA_VERSION,
            _bytes_exact(project_id, _PROJECT_ID_BYTES, "project id"),
            _epoch(epoch),
            root,
            _profile_digest(profile),
            len(records),
            len(graph_secret),
        )
    )
    for record in sorted(records, key=lambda item: item.object_id):
        body.extend(
            _RECORD.pack(
                record.object_id,
                record.artifact_digest,
                record.locator,
            )
        )
    body.extend(graph_secret)
    return bytes(body)


def _decode_root(
    plaintext: bytes,
    *,
    profile: CryptoProfileV1,
    expected_project_id: bytes,
    expected_epoch: int,
) -> tuple[bytes, tuple[ObjectSpaceRecord, ...], bytes]:
    if not isinstance(plaintext, bytes) or len(plaintext) < _HEADER.size:
        _fail("sealed root capsule plaintext is truncated")
    (
        magic,
        version,
        project_id,
        epoch,
        root_object_id,
        profile_digest,
        object_count,
        graph_bytes,
    ) = _HEADER.unpack_from(plaintext, 0)
    if magic != _MAGIC or version != SPACE_SCHEMA_VERSION:
        _fail("sealed root capsule format mismatch")
    trusted_project = _bytes_exact(
        expected_project_id, _PROJECT_ID_BYTES, "expected project id"
    )
    if not hmac.compare_digest(project_id, trusted_project):
        _fail("sealed root belongs to another trusted project")
    if epoch != _epoch(expected_epoch):
        _fail("sealed root epoch is stale or from another temporal reality")
    if not hmac.compare_digest(profile_digest, _profile_digest(profile)):
        _fail("sealed root crypto profile does not match the trusted profile")
    if not 1 <= object_count <= MAX_OBJECTS:
        _fail("sealed root object count is outside policy")
    if graph_bytes > MAX_GRAPH_SECRET_BYTES:
        _fail("sealed root graph secret exceeds policy")
    expected_size = _HEADER.size + (object_count * _RECORD.size) + graph_bytes
    if len(plaintext) != expected_size:
        _fail("sealed root capsule length is non-canonical")

    offset = _HEADER.size
    records: list[ObjectSpaceRecord] = []
    ids: set[bytes] = set()
    locators: set[bytes] = set()
    for _ in range(object_count):
        object_id, artifact_digest, locator = _RECORD.unpack_from(plaintext, offset)
        offset += _RECORD.size
        if object_id in ids or locator in locators:
            _fail("sealed root contains duplicate object identity or locator")
        ids.add(object_id)
        locators.add(locator)
        records.append(ObjectSpaceRecord(object_id, artifact_digest, locator))
    if root_object_id not in ids:
        _fail("sealed root identity is absent from object records")
    graph_secret = plaintext[offset:]
    return root_object_id, tuple(records), graph_secret


def _safe_open(provider: ObjectSpaceCryptoProvider, **kwargs) -> bytes:
    try:
        plaintext = provider.open(**kwargs)
    except Exception as error:
        raise ObjectSpaceError("object-space cryptographic open failed") from error
    if not isinstance(plaintext, bytes):
        _fail("crypto provider returned a non-bytes plaintext")
    return plaintext


def _safe_seal(provider: ObjectSpaceCryptoProvider, **kwargs) -> bytes:
    try:
        ciphertext = provider.seal(**kwargs)
    except Exception as error:
        raise ObjectSpaceError("object-space cryptographic seal failed") from error
    if not isinstance(ciphertext, bytes) or not ciphertext:
        _fail("crypto provider returned an empty or non-bytes ciphertext")
    return ciphertext


def _list_opaque(directory_fd: int) -> tuple[str, ...]:
    names = tuple(sorted(os.listdir(directory_fd)))
    for name in names:
        if _LOCATOR_RE.fullmatch(name) is None:
            _fail("k1 contains a non-opaque physical name")
    return names


def create_object_space_project(
    destination: str | Path,
    *,
    provider: ObjectSpaceCryptoProvider,
    temporal_key: bytes,
    objects: Mapping[bytes, bytes],
    root_object_id: bytes,
    graph_secret: bytes = b"",
    profile: CryptoProfileV1 = OBJECT_SPACE_PQ1,
    temporal_policy: TemporalAccessPolicy = TemporalAccessPolicy(),
    now: float | int | None = None,
    project_id: bytes | None = None,
) -> tuple[ObjectSpaceProject, bytes]:
    """Create a canonical k0/k1 project and return its current temporal handle."""

    _require_secure_platform()
    crypto = require_profile(provider, profile)
    canonical = _canonical_objects(objects)
    root_id = _bytes_exact(root_object_id, _OBJECT_ID_BYTES, "root object id")
    if root_id not in {item[0] for item in canonical}:
        _fail("root object id is not present in object payloads")
    project = (
        _fresh_nonzero(_PROJECT_ID_BYTES)
        if project_id is None
        else _bytes_exact(project_id, _PROJECT_ID_BYTES, "project id")
    )
    epoch = 1

    root = _absolute_no_symlink_resolution(destination)
    existed = root.exists() or root.is_symlink()
    if not existed:
        root.mkdir(parents=True, mode=0o700)

    root_fd: int | None = None
    store_fd: int | None = None
    created_names: list[str] = []
    root_identity: tuple[int, int] | None = None
    success = False
    try:
        root_fd = _open_directory_path(root, "object-space project root")
        info = os.fstat(root_fd)
        root_identity = (info.st_dev, info.st_ino)
        if os.listdir(root_fd):
            _fail(f"object-space destination is not empty: {root}")
        os.mkdir(OBJECT_STORE_NAME, 0o700, dir_fd=root_fd)
        store_fd = _open_directory_at(root_fd, OBJECT_STORE_NAME, "k1 object store")

        excluded: set[bytes] = set()
        records: list[ObjectSpaceRecord] = []
        for object_id, payload in canonical:
            locator = _fresh_locator(excluded)
            digest = hashlib.sha256(payload).digest()
            sealed = _safe_seal(
                crypto,
                purpose=_OBJECT_PURPOSE,
                associated_data=_object_aad(project, epoch, object_id, locator),
                plaintext=payload,
            )
            if len(sealed) > MAX_SEALED_OBJECT_BYTES:
                _fail("sealed object exceeds object-space ciphertext budget")
            name = locator.hex()
            _write_exclusive_at(store_fd, name, sealed)
            created_names.append(name)
            records.append(ObjectSpaceRecord(object_id, digest, locator))
        os.fsync(store_fd)

        root_plaintext = _encode_root(
            profile=profile,
            project_id=project,
            epoch=epoch,
            root_object_id=root_id,
            records=tuple(records),
            graph_secret=graph_secret,
        )
        sealed_root = _safe_seal(
            crypto,
            purpose=_ROOT_PURPOSE,
            associated_data=_root_aad(project, epoch),
            plaintext=root_plaintext,
        )
        if len(sealed_root) > MAX_SEALED_ROOT_BYTES:
            _fail("sealed k0 exceeds root-capsule ciphertext budget")
        _write_exclusive_at(root_fd, ROOT_CAPSULE_NAME, sealed_root)
        os.fsync(root_fd)
        success = True
    finally:
        if not success:
            if root_fd is not None:
                try:
                    _unlink_at(root_fd, ROOT_CAPSULE_NAME)
                except OSError:
                    pass
            if store_fd is not None:
                for name in created_names:
                    try:
                        _unlink_at(store_fd, name)
                    except OSError:
                        pass
                os.close(store_fd)
                store_fd = None
            if root_fd is not None:
                try:
                    os.rmdir(OBJECT_STORE_NAME, dir_fd=root_fd)
                except OSError:
                    pass
        if store_fd is not None:
            os.close(store_fd)
        if root_fd is not None:
            os.close(root_fd)
        if not success and not existed and root_identity is not None:
            _safe_remove_created_root(root, root_identity)

    if not success:
        _fail("object-space project creation failed")
    handle = issue_temporal_handle(
        temporal_key=temporal_key,
        project_id=project,
        epoch=epoch,
        now=now,
        policy=temporal_policy,
    )
    return (
        load_object_space_project(
            root,
            provider=crypto,
            temporal_key=temporal_key,
            temporal_handle=handle,
            expected_project_id=project,
            expected_epoch=epoch,
            profile=profile,
            temporal_policy=temporal_policy,
            now=now,
        ),
        handle,
    )


def load_object_space_project(
    path: str | Path,
    *,
    provider: ObjectSpaceCryptoProvider,
    temporal_key: bytes,
    temporal_handle: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    profile: CryptoProfileV1 = OBJECT_SPACE_PQ1,
    temporal_policy: TemporalAccessPolicy = TemporalAccessPolicy(),
    now: float | int | None = None,
) -> ObjectSpaceProject:
    """Load only objects authorized by sealed k0; opaque unreferenced cells are inert."""

    _require_secure_platform()
    crypto = require_profile(provider, profile)
    project = _bytes_exact(expected_project_id, _PROJECT_ID_BYTES, "expected project id")
    epoch = _epoch(expected_epoch)
    verify_temporal_handle(
        temporal_handle,
        temporal_key=temporal_key,
        project_id=project,
        epoch=epoch,
        now=now,
        policy=temporal_policy,
    )

    root = _absolute_no_symlink_resolution(path)
    root_fd = _open_directory_path(root, "object-space project root")
    store_fd: int | None = None
    try:
        store_fd = _open_directory_at(root_fd, OBJECT_STORE_NAME, "k1 object store")
        sealed_root = _read_regular_at(
            root_fd,
            ROOT_CAPSULE_NAME,
            label="sealed k0 root capsule",
            max_bytes=MAX_SEALED_ROOT_BYTES,
        )
        root_plaintext = _safe_open(
            crypto,
            purpose=_ROOT_PURPOSE,
            associated_data=_root_aad(project, epoch),
            ciphertext=sealed_root,
        )
        root_object_id, records, graph_secret = _decode_root(
            root_plaintext,
            profile=profile,
            expected_project_id=project,
            expected_epoch=epoch,
        )

        referenced = {record.locator_text for record in records}
        physical = set(_list_opaque(store_fd))
        missing = referenced - physical
        if missing:
            _fail("sealed k0 references missing k1 object cells")

        payloads: dict[bytes, bytes] = {}
        for record in records:
            sealed = _read_regular_at(
                store_fd,
                record.locator_text,
                label="sealed k1 object cell",
                max_bytes=MAX_SEALED_OBJECT_BYTES,
            )
            plaintext = _safe_open(
                crypto,
                purpose=_OBJECT_PURPOSE,
                associated_data=_object_aad(
                    project, epoch, record.object_id, record.locator
                ),
                ciphertext=sealed,
            )
            if len(plaintext) > MAX_SOURCE_BYTES:
                _fail("opened object exceeds object-space plaintext budget")
            digest = hashlib.sha256(plaintext).digest()
            if not hmac.compare_digest(digest, record.artifact_digest):
                _fail("opened object digest does not match sealed k0 authority")
            payloads[record.object_id] = plaintext

        unreferenced = tuple(sorted(physical - referenced))
        return ObjectSpaceProject(
            root=root,
            project_id=project,
            epoch=epoch,
            root_object_id=root_object_id,
            records=records,
            graph_secret=graph_secret,
            object_payloads=payloads,
            unreferenced_locators=unreferenced,
        )
    finally:
        if store_fd is not None:
            os.close(store_fd)
        os.close(root_fd)


def rotate_object_space_epoch(
    path: str | Path,
    *,
    provider: ObjectSpaceCryptoProvider,
    temporal_key: bytes,
    temporal_handle: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    profile: CryptoProfileV1 = OBJECT_SPACE_PQ1,
    temporal_policy: TemporalAccessPolicy = TemporalAccessPolicy(),
    now: float | int | None = None,
) -> tuple[ObjectSpaceProject, bytes]:
    """Rotate every physical locator and invalidate the previous temporal epoch."""

    current = load_object_space_project(
        path,
        provider=provider,
        temporal_key=temporal_key,
        temporal_handle=temporal_handle,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
        profile=profile,
        temporal_policy=temporal_policy,
        now=now,
    )
    crypto = require_profile(provider, profile)
    next_epoch = current.epoch + 1
    if next_epoch > (1 << 64) - 1:
        _fail("object-space epoch exhausted uint64")

    root_fd = _open_directory_path(current.root, "object-space project root")
    store_fd: int | None = None
    new_names: list[str] = []
    switched = False
    try:
        store_fd = _open_directory_at(root_fd, OBJECT_STORE_NAME, "k1 object store")
        excluded = {
            bytes.fromhex(name)
            for name in _list_opaque(store_fd)
        }
        records: list[ObjectSpaceRecord] = []
        for old in current.records:
            payload = current.object_payloads[old.object_id]
            locator = _fresh_locator(excluded)
            sealed = _safe_seal(
                crypto,
                purpose=_OBJECT_PURPOSE,
                associated_data=_object_aad(
                    current.project_id, next_epoch, old.object_id, locator
                ),
                plaintext=payload,
            )
            if len(sealed) > MAX_SEALED_OBJECT_BYTES:
                _fail("rotated sealed object exceeds ciphertext budget")
            name = locator.hex()
            _write_exclusive_at(store_fd, name, sealed)
            new_names.append(name)
            records.append(
                ObjectSpaceRecord(
                    old.object_id,
                    hashlib.sha256(payload).digest(),
                    locator,
                )
            )
        os.fsync(store_fd)

        root_plaintext = _encode_root(
            profile=profile,
            project_id=current.project_id,
            epoch=next_epoch,
            root_object_id=current.root_object_id,
            records=tuple(records),
            graph_secret=current.graph_secret,
        )
        sealed_root = _safe_seal(
            crypto,
            purpose=_ROOT_PURPOSE,
            associated_data=_root_aad(current.project_id, next_epoch),
            plaintext=root_plaintext,
        )
        pending = _fresh_locator(excluded).hex()
        _write_exclusive_at(store_fd, pending, sealed_root)
        os.fsync(store_fd)
        os.rename(
            pending,
            ROOT_CAPSULE_NAME,
            src_dir_fd=store_fd,
            dst_dir_fd=root_fd,
        )
        os.fsync(root_fd)
        switched = True

        # Old cells are now non-authoritative.  Cleanup is best-effort: if a crash
        # leaves opaque extras, load reports them as inert unreferenced locators.
        for old in current.records:
            try:
                _unlink_at(store_fd, old.locator_text)
            except OSError:
                pass
        os.fsync(store_fd)
    finally:
        if not switched and store_fd is not None:
            for name in new_names:
                try:
                    _unlink_at(store_fd, name)
                except OSError:
                    pass
        if store_fd is not None:
            os.close(store_fd)
        os.close(root_fd)

    if not switched:
        _fail("object-space epoch rotation failed before k0 authority switch")
    next_handle = issue_temporal_handle(
        temporal_key=temporal_key,
        project_id=current.project_id,
        epoch=next_epoch,
        now=now,
        policy=temporal_policy,
    )
    return (
        load_object_space_project(
            current.root,
            provider=crypto,
            temporal_key=temporal_key,
            temporal_handle=next_handle,
            expected_project_id=current.project_id,
            expected_epoch=next_epoch,
            profile=profile,
            temporal_policy=temporal_policy,
            now=now,
        ),
        next_handle,
    )
