"""Third adversarial hardening round for Object Space v1.

Object Space is not allowed to rely on creation-time chmod alone. Every admitted
project directory and every authoritative/readable cell is revalidated against
the current OS principal before use.

Opened plaintext is also bounded immediately after the external crypto provider
returns, before root parsing or later object processing.

Threat boundary: this blocks cross-principal filesystem mutation/reconnaissance
through permissive Unix modes and hard-link aliases. It does not claim isolation
from another compromised process running as the same effective UID, a hostile
kernel, a hostile mount namespace, or arbitrary computation performed inside a
provider that is itself compromised.
"""

from __future__ import annotations

import os
import stat

from . import object_space_v1 as _space

_INSTALLED = False
_ORIGINAL_OPEN_DIRECTORY_PATH = None
_ORIGINAL_OPEN_DIRECTORY_AT = None
_ORIGINAL_SAFE_OPEN = None

_MAX_ROOT_PLAINTEXT_V1 = (
    _space._HEADER.size
    + (_space.MAX_OBJECTS * _space._RECORD.size)
    + _space.MAX_GRAPH_SECRET_BYTES
)


def _effective_uid() -> int | None:
    getter = getattr(os, "geteuid", None)
    return getter() if getter is not None else None


def _require_owned_private_directory(fd: int, label: str) -> None:
    try:
        info = os.fstat(fd)
    except OSError as error:
        raise _space.ObjectSpaceError(f"{label} metadata unavailable: {error}") from error
    if not stat.S_ISDIR(info.st_mode):
        _space._fail(f"{label} must remain a directory")
    uid = _effective_uid()
    if uid is not None and info.st_uid != uid:
        _space._fail(f"{label} must be owned by the active OS principal")
    if stat.S_IMODE(info.st_mode) & 0o077:
        _space._fail(f"{label} must not grant group/world filesystem access")


def _open_private_directory_path(path, label: str) -> int:
    assert _ORIGINAL_OPEN_DIRECTORY_PATH is not None
    fd = _ORIGINAL_OPEN_DIRECTORY_PATH(path, label)
    try:
        _require_owned_private_directory(fd, label)
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_private_directory_at(parent_fd: int, name: str, label: str) -> int:
    assert _ORIGINAL_OPEN_DIRECTORY_AT is not None
    fd = _ORIGINAL_OPEN_DIRECTORY_AT(parent_fd, name, label)
    try:
        _require_owned_private_directory(fd, label)
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_private_regular_at(
    directory_fd: int,
    name: str,
    *,
    label: str,
    max_bytes: int,
    exact_bytes: int | None = None,
) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise _space.ObjectSpaceError(f"{label} cannot be opened safely: {error}") from error
    try:
        try:
            before = os.fstat(fd)
        except OSError as error:
            raise _space.ObjectSpaceError(f"{label} metadata unavailable: {error}") from error
        if not stat.S_ISREG(before.st_mode):
            _space._fail(f"{label} must be a regular non-symlink file")
        if before.st_nlink != 1:
            _space._fail(f"{label} must have exactly one filesystem link")
        uid = _effective_uid()
        if uid is not None and before.st_uid != uid:
            _space._fail(f"{label} must be owned by the active OS principal")
        if stat.S_IMODE(before.st_mode) & 0o022:
            _space._fail(f"{label} must not be group/world writable")
        if before.st_size > max_bytes:
            _space._fail(f"{label} exceeds the {max_bytes}-byte limit")
        if exact_bytes is not None and before.st_size != exact_bytes:
            _space._fail(f"{label} must be exactly {exact_bytes} bytes")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            try:
                chunk = os.read(fd, min(65536, remaining))
            except OSError as error:
                raise _space.ObjectSpaceError(f"{label} read failed: {error}") from error
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            _space._fail(f"{label} exceeds the {max_bytes}-byte limit")
        if exact_bytes is not None and len(payload) != exact_bytes:
            _space._fail(f"{label} length changed while reading")

        try:
            after = os.fstat(fd)
        except OSError as error:
            raise _space.ObjectSpaceError(f"{label} final metadata unavailable: {error}") from error
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_nlink,
            stat.S_IMODE(before.st_mode),
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_nlink,
            stat.S_IMODE(after.st_mode),
        ):
            _space._fail(f"{label} identity or permissions changed while being read")
        return payload
    finally:
        os.close(fd)


def _bounded_safe_open(provider, **kwargs) -> bytes:
    assert _ORIGINAL_SAFE_OPEN is not None
    plaintext = _ORIGINAL_SAFE_OPEN(provider, **kwargs)
    purpose = kwargs.get("purpose")
    if purpose == _space._ROOT_PURPOSE:
        limit = _MAX_ROOT_PLAINTEXT_V1
    elif purpose == _space._OBJECT_PURPOSE:
        limit = _space.MAX_SOURCE_BYTES
    else:
        _space._fail("crypto provider open used an unknown Object Space purpose")
    if len(plaintext) > limit:
        _space._fail("crypto provider returned plaintext outside Object Space policy")
    return plaintext


def install_object_space_redteam_round3_v1() -> None:
    global _INSTALLED, _ORIGINAL_OPEN_DIRECTORY_PATH, _ORIGINAL_OPEN_DIRECTORY_AT, _ORIGINAL_SAFE_OPEN
    if _INSTALLED:
        return
    _ORIGINAL_OPEN_DIRECTORY_PATH = _space._open_directory_path
    _ORIGINAL_OPEN_DIRECTORY_AT = _space._open_directory_at
    _ORIGINAL_SAFE_OPEN = _space._safe_open
    _space._open_directory_path = _open_private_directory_path
    _space._open_directory_at = _open_private_directory_at
    _space._read_regular_at = _read_private_regular_at
    _space._safe_open = _bounded_safe_open
    _INSTALLED = True
