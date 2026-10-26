"""Adversarial hardening for Koschei Object Space v1.

This guard closes the first red-team findings against the experimental object-space
implementation:

* epoch rotation is serialized on the admitted project-root descriptor;
* k0 is re-opened and authenticated only after the exclusive transition lock;
* mutation never reopens the project through a pathname after admission;
* the project path must still name the admitted inode immediately before k0 switch;
* every k1 entry must be a regular, non-symlink, single-link opaque cell;
* decoded k0 records must be canonical and use non-zero fixed-width fields; and
* a pending root capsule is removed on every pre-switch failure.

The lock is coordination between authorized Koschei writers, not cryptographic
authority. A filesystem attacker may ignore the advisory lock and cause denial of
service, but cannot forge a sealed k0 through this mechanism.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat

try:
    import fcntl
except ImportError:  # pragma: no cover - secure platform gate fails closed.
    fcntl = None

from . import object_space_v1 as _space
from .crypto_agility_v1 import require_profile
from .temporal_access_v1 import issue_temporal_handle, verify_temporal_handle

_INSTALLED = False
_ORIGINAL_DECODE_ROOT = None


def _strict_list_opaque(directory_fd: int) -> tuple[str, ...]:
    names = tuple(sorted(os.listdir(directory_fd)))
    for name in names:
        if _space._LOCATOR_RE.fullmatch(name) is None:
            _space._fail("k1 contains a non-opaque physical name")
        try:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as error:
            raise _space.ObjectSpaceError(
                f"k1 cell metadata cannot be inspected safely: {error}"
            ) from error
        if not stat.S_ISREG(info.st_mode):
            _space._fail("k1 contains a non-regular or symlink physical cell")
        if info.st_nlink != 1:
            _space._fail("k1 physical cells must have exactly one filesystem link")
    return names


def _strict_decode_root(*args, **kwargs):
    root_object_id, records, graph_secret = _ORIGINAL_DECODE_ROOT(*args, **kwargs)
    _space._bytes_exact(root_object_id, _space._OBJECT_ID_BYTES, "root object id")
    for record in records:
        _space._bytes_exact(record.object_id, _space._OBJECT_ID_BYTES, "object id")
        _space._bytes_exact(record.artifact_digest, _space._DIGEST_BYTES, "artifact digest")
        _space._bytes_exact(record.locator, _space._LOCATOR_BYTES, "locator")
    canonical = tuple(sorted(records, key=lambda item: item.object_id))
    if records != canonical:
        _space._fail("sealed k0 object records are not canonical")
    return root_object_id, records, graph_secret


def _root_path_matches_fd(root: Path, root_fd: int) -> bool:
    try:
        path_info = root.lstat()
        descriptor_info = os.fstat(root_fd)
    except OSError:
        return False
    return (
        stat.S_ISDIR(path_info.st_mode)
        and not stat.S_ISLNK(path_info.st_mode)
        and (path_info.st_dev, path_info.st_ino)
        == (descriptor_info.st_dev, descriptor_info.st_ino)
    )


def _commit_root_switch(*, pending: str, store_fd: int, root_fd: int) -> None:
    """Single atomic authority switch seam, isolated for precise fault injection."""
    os.rename(
        pending,
        _space.ROOT_CAPSULE_NAME,
        src_dir_fd=store_fd,
        dst_dir_fd=root_fd,
    )


def _load_from_admitted_handles(
    *, root: Path, root_fd: int, store_fd: int, crypto,
    temporal_key: bytes, temporal_handle: bytes,
    expected_project_id: bytes, expected_epoch: int,
    profile, temporal_policy, now,
) -> _space.ObjectSpaceProject:
    project = _space._bytes_exact(expected_project_id, _space._PROJECT_ID_BYTES, "expected project id")
    epoch = _space._epoch(expected_epoch)
    verify_temporal_handle(
        temporal_handle,
        temporal_key=temporal_key,
        project_id=project,
        epoch=epoch,
        now=now,
        policy=temporal_policy,
    )

    sealed_root = _space._read_regular_at(
        root_fd, _space.ROOT_CAPSULE_NAME,
        label="sealed k0 root capsule", max_bytes=_space.MAX_SEALED_ROOT_BYTES,
    )
    root_plaintext = _space._safe_open(
        crypto,
        purpose=_space._ROOT_PURPOSE,
        associated_data=_space._root_aad(project, epoch),
        ciphertext=sealed_root,
    )
    root_object_id, records, graph_secret = _space._decode_root(
        root_plaintext,
        profile=profile,
        expected_project_id=project,
        expected_epoch=epoch,
    )

    referenced = {record.locator_text for record in records}
    physical = set(_space._list_opaque(store_fd))
    missing = referenced - physical
    if missing:
        _space._fail("sealed k0 references missing k1 object cells")

    payloads: dict[bytes, bytes] = {}
    for record in records:
        sealed = _space._read_regular_at(
            store_fd, record.locator_text,
            label="sealed k1 object cell", max_bytes=_space.MAX_SEALED_OBJECT_BYTES,
        )
        plaintext = _space._safe_open(
            crypto,
            purpose=_space._OBJECT_PURPOSE,
            associated_data=_space._object_aad(project, epoch, record.object_id, record.locator),
            ciphertext=sealed,
        )
        if len(plaintext) > _space.MAX_SOURCE_BYTES:
            _space._fail("opened object exceeds object-space plaintext budget")
        digest = hashlib.sha256(plaintext).digest()
        if not hmac.compare_digest(digest, record.artifact_digest):
            _space._fail("opened object digest does not match sealed k0 authority")
        payloads[record.object_id] = plaintext

    return _space.ObjectSpaceProject(
        root=root,
        project_id=project,
        epoch=epoch,
        root_object_id=root_object_id,
        records=records,
        graph_secret=graph_secret,
        object_payloads=payloads,
        unreferenced_locators=tuple(sorted(physical - referenced)),
    )


def _locked_rotate_object_space_epoch(
    path: str | Path,
    *, provider, temporal_key: bytes, temporal_handle: bytes,
    expected_project_id: bytes, expected_epoch: int,
    profile=_space.OBJECT_SPACE_PQ1,
    temporal_policy=_space.TemporalAccessPolicy(),
    now: float | int | None = None,
):
    """Rotate one admitted reality with lock-after-admission reauthentication."""
    _space._require_secure_platform()
    if fcntl is None:
        _space._fail("object-space rotation requires advisory descriptor locking")
    crypto = require_profile(provider, profile)
    root = _space._absolute_no_symlink_resolution(path)
    root_fd = _space._open_directory_path(root, "object-space project root")
    store_fd: int | None = None
    new_names: list[str] = []
    pending: str | None = None
    switched = False
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        store_fd = _space._open_directory_at(root_fd, _space.OBJECT_STORE_NAME, "k1 object store")
        current = _load_from_admitted_handles(
            root=root, root_fd=root_fd, store_fd=store_fd, crypto=crypto,
            temporal_key=temporal_key, temporal_handle=temporal_handle,
            expected_project_id=expected_project_id, expected_epoch=expected_epoch,
            profile=profile, temporal_policy=temporal_policy, now=now,
        )
        next_epoch = current.epoch + 1
        if next_epoch > (1 << 64) - 1:
            _space._fail("object-space epoch exhausted uint64")

        excluded = {bytes.fromhex(name) for name in _space._list_opaque(store_fd)}
        records: list[_space.ObjectSpaceRecord] = []
        for old in current.records:
            payload = current.object_payloads[old.object_id]
            locator = _space._fresh_locator(excluded)
            sealed = _space._safe_seal(
                crypto,
                purpose=_space._OBJECT_PURPOSE,
                associated_data=_space._object_aad(current.project_id, next_epoch, old.object_id, locator),
                plaintext=payload,
            )
            if len(sealed) > _space.MAX_SEALED_OBJECT_BYTES:
                _space._fail("rotated sealed object exceeds ciphertext budget")
            name = locator.hex()
            _space._write_exclusive_at(store_fd, name, sealed)
            new_names.append(name)
            records.append(_space.ObjectSpaceRecord(old.object_id, hashlib.sha256(payload).digest(), locator))
        os.fsync(store_fd)

        root_plaintext = _space._encode_root(
            profile=profile,
            project_id=current.project_id,
            epoch=next_epoch,
            root_object_id=current.root_object_id,
            records=tuple(records),
            graph_secret=current.graph_secret,
        )
        sealed_root = _space._safe_seal(
            crypto,
            purpose=_space._ROOT_PURPOSE,
            associated_data=_space._root_aad(current.project_id, next_epoch),
            plaintext=root_plaintext,
        )
        if len(sealed_root) > _space.MAX_SEALED_ROOT_BYTES:
            _space._fail("rotated sealed k0 exceeds root-capsule ciphertext budget")
        pending = _space._fresh_locator(excluded).hex()
        _space._write_exclusive_at(store_fd, pending, sealed_root)
        os.fsync(store_fd)

        if not _root_path_matches_fd(root, root_fd):
            _space._fail("project root path identity changed before k0 authority switch")

        _commit_root_switch(pending=pending, store_fd=store_fd, root_fd=root_fd)
        pending = None
        os.fsync(root_fd)
        switched = True

        for old in current.records:
            try:
                _space._unlink_at(store_fd, old.locator_text)
            except OSError:
                pass
        os.fsync(store_fd)

        next_handle = issue_temporal_handle(
            temporal_key=temporal_key,
            project_id=current.project_id,
            epoch=next_epoch,
            now=now,
            policy=temporal_policy,
        )
        next_project = _load_from_admitted_handles(
            root=root, root_fd=root_fd, store_fd=store_fd, crypto=crypto,
            temporal_key=temporal_key, temporal_handle=next_handle,
            expected_project_id=current.project_id, expected_epoch=next_epoch,
            profile=profile, temporal_policy=temporal_policy, now=now,
        )
        return next_project, next_handle
    finally:
        if not switched and store_fd is not None:
            if pending is not None:
                try:
                    _space._unlink_at(store_fd, pending)
                except OSError:
                    pass
            for name in new_names:
                try:
                    _space._unlink_at(store_fd, name)
                except OSError:
                    pass
        if store_fd is not None:
            os.close(store_fd)
        try:
            fcntl.flock(root_fd, fcntl.LOCK_UN)
        finally:
            os.close(root_fd)


def install_object_space_adversarial_guard_v1() -> None:
    global _INSTALLED, _ORIGINAL_DECODE_ROOT
    if _INSTALLED:
        return
    _ORIGINAL_DECODE_ROOT = _space._decode_root
    _space._decode_root = _strict_decode_root
    _space._list_opaque = _strict_list_opaque
    _space.rotate_object_space_epoch = _locked_rotate_object_space_epoch
    _INSTALLED = True
