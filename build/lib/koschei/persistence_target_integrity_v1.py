"""Final-object identity hardening for interpreter persistence v1.

V1 rejects hard-link aliases and uses O_NONBLOCK for the real load open. The
latter closes the race where a target validated as regular is replaced by a FIFO
before the data descriptor is opened; fstat after open still decides admissibility.
"""

from __future__ import annotations

import errno
import os
import stat

from . import bounded_persistence_v1 as _persist
from . import interpreter as _runtime
from .persistence_authority_v1 import PersistCaps

_INSTALLED = False
_ORIGINAL_SAFE_TARGET_SHAPE = None


def _safe_target_shape(parent_fd: int, name: str) -> _runtime.KsError | None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        return _persist._io_error(f"target metadata read failed: {error}")

    if stat.S_ISLNK(info.st_mode):
        return _persist._contract_error("persistence target may not be a symbolic link")
    if not stat.S_ISREG(info.st_mode):
        return _persist._contract_error(
            "persistence target must be a regular file when it exists"
        )
    if info.st_nlink != 1:
        return _persist._contract_error(
            "persistence target must have exactly one hard-link name"
        )
    return None


def _load(self: PersistCaps) -> str | _runtime.KsError:
    deadline = _persist._deadline(self.policy)
    expired = _persist._check_deadline(deadline, "load-start")
    if expired is not None:
        return expired

    parent_fd, failure = _persist._parent_duplicate(self)
    if failure is not None:
        return failure
    assert parent_fd is not None
    try:
        shape_failure = _persist._safe_target_shape(parent_fd, self._name)
        if shape_failure is not None:
            return shape_failure
        expired = _persist._check_deadline(deadline, "load-open")
        if expired is not None:
            return expired
        try:
            fd = os.open(
                self._name,
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return _persist._io_error("persistence state object does not exist")
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return _persist._contract_error(
                    "persistence target may not be a symbolic link"
                )
            return _persist._io_error(f"persistence state open failed: {error}")

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return _persist._contract_error(
                    "opened persistence target is not a regular file"
                )
            if info.st_nlink != 1:
                return _persist._contract_error(
                    "opened persistence target must have exactly one hard-link name"
                )
            if info.st_size > self.policy.max_bytes:
                return _persist._budget_error("persisted state exceeds max_bytes")

            buffer = bytearray()
            while True:
                expired = _persist._check_deadline(deadline, "load-read")
                if expired is not None:
                    return expired
                remaining = self.policy.max_bytes + 1 - len(buffer)
                chunk = os.read(fd, min(_persist._CHUNK_BYTES, remaining))
                expired = _persist._check_deadline(deadline, "load-read-complete")
                if expired is not None:
                    return expired
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > self.policy.max_bytes:
                    return _persist._budget_error("persisted state exceeds max_bytes")
        except OSError as error:
            return _persist._io_error(f"persistence state read failed: {error}")
        finally:
            os.close(fd)

        try:
            return bytes(buffer).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _persist._contract_error("persisted state is not valid UTF-8")
    finally:
        os.close(parent_fd)


def install_persistence_target_integrity_v1() -> None:
    global _INSTALLED, _ORIGINAL_SAFE_TARGET_SHAPE
    if _INSTALLED:
        return

    if not hasattr(os, "O_NONBLOCK"):
        _persist._PERSIST_FD_SUPPORTED = False

    _ORIGINAL_SAFE_TARGET_SHAPE = _persist._safe_target_shape
    _persist._safe_target_shape = _safe_target_shape
    PersistCaps.load = _load
    _INSTALLED = True
