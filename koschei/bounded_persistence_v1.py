"""Bounded exact-object persistence runtime v1.

PersistCaps is intentionally narrower than DiskCaps. It is anchored to one parent
directory descriptor and one basename at token construction time. Callers cannot
supply another path to load/commit.

Commit protocol:
    bounded UTF-8 -> same-directory temp -> full write -> fsync(temp)
    -> atomic replace -> fsync(parent directory)

A failure after atomic replace but before durability confirmation returns a
separate KS3423 state-uncertain error. It is never reported as a clean rollback.

The deadline in v1 is a cooperative sequence deadline checked before and after
filesystem syscalls; Python cannot safely preempt a blocking kernel filesystem
call. The stdlib catalog therefore remains reserved until a sealed cross-backend
I/O deadline model exists.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
import time
from typing import Any

from . import interpreter as _runtime
from . import semantic as _semantic
from .persistence_authority_v1 import PersistCaps, PersistPolicy

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None

_CHUNK_BYTES = 64 * 1024

_PERSIST_FD_SUPPORTED = (
    hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.replace in os.supports_dir_fd
)


def _contract_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3420: {message}")


def _budget_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3421: {message}")


def _deadline_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3422: {message}")


def _uncertain_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3423: {message}")


def _io_error(message: str) -> _runtime.KsError:
    return _runtime.KsError(f"KS3424: {message}")


def _deadline(policy: PersistPolicy) -> float:
    return time.monotonic() + (policy.deadline_ms / 1000.0)


def _check_deadline(deadline: float, stage: str) -> _runtime.KsError | None:
    if time.monotonic() > deadline:
        return _deadline_error(f"persistence sequence deadline exceeded at {stage}")
    return None


def _open_exact_parent(path: str) -> tuple[int, str]:
    """Open the exact parent without following any directory symlink component."""
    if not _PERSIST_FD_SUPPORTED:
        raise OSError(errno.ENOTSUP, "descriptor-relative persistence ABI unavailable")

    parent = os.path.dirname(path)
    name = os.path.basename(path)
    components = [part for part in parent.split(os.sep) if part]

    current = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in components:
            nxt = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = nxt
        return current, name
    except Exception:
        os.close(current)
        raise


def _safe_target_shape(parent_fd: int, name: str) -> _runtime.KsError | None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        return _io_error(f"target metadata read failed: {error}")

    if stat.S_ISLNK(info.st_mode):
        return _contract_error("persistence target may not be a symbolic link")
    if not stat.S_ISREG(info.st_mode):
        return _contract_error("persistence target must be a regular file when it exists")
    return None


def _persist_init(self: PersistCaps, policy: PersistPolicy) -> None:
    self.policy = policy
    self._parent_fd = None
    self._name = os.path.basename(policy.path)
    self._open_error = None
    try:
        parent_fd, name = _open_exact_parent(policy.path)
        self._parent_fd = parent_fd
        self._name = name
    except OSError as error:
        self._open_error = error


def _persist_del(self: PersistCaps) -> None:
    handle = getattr(self, "_parent_fd", None)
    if handle is None:
        return
    try:
        os.close(handle)
    except OSError:
        pass
    self._parent_fd = None


def _parent_duplicate(self: PersistCaps) -> tuple[int | None, _runtime.KsError | None]:
    handle = getattr(self, "_parent_fd", None)
    if handle is None:
        error = getattr(self, "_open_error", None)
        if error is not None:
            return None, _io_error(f"persistence parent could not be anchored: {error}")
        return None, _io_error("persistence parent descriptor is unavailable")
    try:
        return os.dup(handle), None
    except OSError as error:
        return None, _io_error(f"persistence parent descriptor could not be duplicated: {error}")


def _load(self: PersistCaps) -> str | _runtime.KsError:
    deadline = _deadline(self.policy)
    expired = _check_deadline(deadline, "load-start")
    if expired is not None:
        return expired

    parent_fd, failure = _parent_duplicate(self)
    if failure is not None:
        return failure
    assert parent_fd is not None
    try:
        shape_failure = _safe_target_shape(parent_fd, self._name)
        if shape_failure is not None:
            return shape_failure
        expired = _check_deadline(deadline, "load-open")
        if expired is not None:
            return expired
        try:
            fd = os.open(
                self._name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return _io_error("persistence state object does not exist")
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                return _contract_error("persistence target may not be a symbolic link")
            return _io_error(f"persistence state open failed: {error}")

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                return _contract_error("opened persistence target is not a regular file")
            if info.st_size > self.policy.max_bytes:
                return _budget_error("persisted state exceeds max_bytes")

            buffer = bytearray()
            while True:
                expired = _check_deadline(deadline, "load-read")
                if expired is not None:
                    return expired
                remaining = self.policy.max_bytes + 1 - len(buffer)
                chunk = os.read(fd, min(_CHUNK_BYTES, remaining))
                expired = _check_deadline(deadline, "load-read-complete")
                if expired is not None:
                    return expired
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > self.policy.max_bytes:
                    return _budget_error("persisted state exceeds max_bytes")
        except OSError as error:
            return _io_error(f"persistence state read failed: {error}")
        finally:
            os.close(fd)

        try:
            return bytes(buffer).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _contract_error("persisted state is not valid UTF-8")
    finally:
        os.close(parent_fd)


def _commit(self: PersistCaps, value: Any):
    if not isinstance(value, str):
        return _contract_error("PersistCaps.commit() value must be String")
    try:
        payload = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return _contract_error("PersistCaps.commit() value is not valid UTF-8")
    if len(payload) > self.policy.max_bytes:
        return _budget_error("commit payload exceeds max_bytes")

    deadline = _deadline(self.policy)
    expired = _check_deadline(deadline, "commit-start")
    if expired is not None:
        return expired

    parent_fd, failure = _parent_duplicate(self)
    if failure is not None:
        return failure
    assert parent_fd is not None

    temp_name: str | None = None
    temp_fd: int | None = None
    replaced = False
    try:
        shape_failure = _safe_target_shape(parent_fd, self._name)
        if shape_failure is not None:
            return shape_failure

        for _attempt in range(16):
            expired = _check_deadline(deadline, "temp-create")
            if expired is not None:
                return expired
            candidate = f".koschei-persist-{secrets.token_hex(16)}"
            try:
                temp_fd = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
                temp_name = candidate
                break
            except FileExistsError:
                continue
            except OSError as error:
                return _io_error(f"persistence temp create failed: {error}")
        if temp_fd is None or temp_name is None:
            return _io_error("persistence temp name allocation exhausted")

        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            expired = _check_deadline(deadline, "temp-write")
            if expired is not None:
                return expired
            try:
                written = os.write(temp_fd, view[offset : offset + _CHUNK_BYTES])
            except OSError as error:
                return _io_error(f"persistence temp write failed: {error}")
            expired = _check_deadline(deadline, "temp-write-complete")
            if expired is not None:
                return expired
            if written <= 0:
                return _io_error("persistence temp write made no progress")
            offset += written

        expired = _check_deadline(deadline, "temp-fsync")
        if expired is not None:
            return expired
        try:
            os.fsync(temp_fd)
        except OSError as error:
            return _io_error(f"persistence temp fsync failed: {error}")
        expired = _check_deadline(deadline, "temp-fsync-complete")
        if expired is not None:
            return expired

        os.close(temp_fd)
        temp_fd = None

        expired = _check_deadline(deadline, "atomic-replace")
        if expired is not None:
            return expired
        try:
            os.replace(
                temp_name,
                self._name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replaced = True
            temp_name = None
        except OSError as error:
            return _io_error(f"persistence atomic replace failed: {error}")

        expired = _check_deadline(deadline, "directory-fsync")
        if expired is not None:
            return _uncertain_error(
                "state was atomically replaced but directory durability was not confirmed before deadline"
            )
        try:
            os.fsync(parent_fd)
        except OSError as error:
            return _uncertain_error(
                f"state was atomically replaced but directory fsync failed: {error}"
            )
        expired = _check_deadline(deadline, "directory-fsync-complete")
        if expired is not None:
            return _uncertain_error(
                "state was atomically replaced but durability confirmation exceeded deadline"
            )
        return _runtime.KsUnit
    finally:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if temp_name is not None and not replaced:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "PersistCaps":
        values = argument_types or []
        if method_name == "load":
            if values:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"PersistCaps.load() 0 argüman bekler, {len(values)} verildi.",
                    location,
                )
            return "String or Error"
        if method_name == "commit":
            if len(values) != 1:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"PersistCaps.commit() 1 argüman bekler, {len(values)} verildi.",
                    location,
                )
            self._require_assignable(
                ("String",),
                values[0],
                "PersistCaps.commit() payload",
                location,
            )
            return "Void or Error"

    return _ORIGINAL_CHECK_METHOD_CALL(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def install_bounded_persistence_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_METHOD_CALL
    if _INSTALLED:
        return

    # PersistCaps instances created after this installer carry a descriptor anchor.
    PersistCaps.__slots__ = ("policy", "_parent_fd", "_name", "_open_error")
    PersistCaps.__init__ = _persist_init
    PersistCaps.__del__ = _persist_del
    PersistCaps.load = _load
    PersistCaps.commit = _commit

    _semantic.NARROWED_METHODS["PersistCaps"] = {
        "load": "String or Error",
        "commit": "Void or Error",
    }

    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call

    _INSTALLED = True
