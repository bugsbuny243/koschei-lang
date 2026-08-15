"""Koschei-native object-identity project reality v1.

This is the first project format that does not use a human-readable entry path,
package manifest, or semantic source filename as authority.

v1 intentionally admits one canonical root object and no imports. Multi-object
projects must use an authenticated object-edge format in a later revision; v1
fails closed instead of falling back to sibling filenames.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import stat
import struct
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - secure v1 fails closed on this platform.
    fcntl = None

from .lexer import LexerError
from .modules import Module, ModuleError, ModuleGraph
from .parser import ParserError, parse

REALITY_DIR_NAME = ".koschei"
REALITY_FILE_NAME = "reality"
MATTER_DIR_NAME = "matter"
REALITY_MAGIC = b"KOSCHEI_REALITY\x00"
REALITY_SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 4 << 20
_ALIAS_BYTES = 16
_ID_BYTES = 16
_DIGEST_BYTES = 32
_HEADER = struct.Struct(">16sB7x16s16s32s32sQ16s")
REALITY_ENVELOPE_BYTES = _HEADER.size + _DIGEST_BYTES
REALITY_SEAL_KEY_BYTES = 32

_POLICY_BYTES_V1 = (
    b"koschei.native-reality/v1\x00"
    b"no-semantic-path-authority\x00"
    b"no-plaintext-manifest\x00"
    b"no-implicit-import-fallback\x00"
    b"descriptor-bound-layout"
)
POLICY_DIGEST_V1 = hashlib.sha256(_POLICY_BYTES_V1).digest()


class NativeRealityError(ValueError):
    """Raised when the native project reality is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class NativeReality:
    project_id: bytes
    root_object_id: bytes
    policy_digest: bytes
    artifact_digest: bytes
    epoch: int
    epoch_alias: bytes

    @property
    def project_id_hex(self) -> str:
        return self.project_id.hex()

    @property
    def root_object_id_hex(self) -> str:
        return self.root_object_id.hex()

    @property
    def artifact_sha256(self) -> str:
        return self.artifact_digest.hex()

    @property
    def epoch_alias_text(self) -> str:
        return self.epoch_alias.hex()


@dataclass(frozen=True, slots=True)
class NativeRealityProject:
    root: Path
    reality_path: Path
    matter_root: Path
    reality: NativeReality
    source_path: Path
    source_text: str
    source_bytes: bytes


def _fail(message: str) -> None:
    raise NativeRealityError(message)


def _require_secure_platform() -> None:
    required_flags = ("O_NOFOLLOW", "O_DIRECTORY")
    if any(not hasattr(os, name) for name in required_flags):
        _fail("native reality v1 requires O_NOFOLLOW and O_DIRECTORY")
    required_dirfd = (os.open, os.mkdir, os.unlink, os.rmdir, os.rename)
    if any(function not in os.supports_dir_fd for function in required_dirfd):
        _fail("native reality v1 requires descriptor-relative filesystem operations")
    if fcntl is None:
        _fail("native reality v1 requires advisory directory locking support")


def _require_bytes(value: object, size: int, field: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != size or not any(value):
        _fail(f"{field} must be exactly {size} non-zero bytes")
    return value


def _seal_key(value: object) -> bytes:
    if (
        not isinstance(value, bytes)
        or len(value) != REALITY_SEAL_KEY_BYTES
        or not any(value)
    ):
        _fail(
            f"reality seal key must be exactly "
            f"{REALITY_SEAL_KEY_BYTES} non-zero bytes"
        )
    return value


def _absolute_no_symlink_resolution(path: str | Path) -> Path:
    return Path(path).absolute()


def _source_bytes(source_text: object) -> bytes:
    if not isinstance(source_text, str):
        _fail("source_text must be a string")
    try:
        payload = source_text.encode("utf-8")
    except UnicodeError as error:
        raise NativeRealityError(f"source is not valid UTF-8: {error}") from error
    if len(payload) > MAX_SOURCE_BYTES:
        _fail(f"source exceeds the {MAX_SOURCE_BYTES}-byte limit")
    return payload


def _parse_single_object_source(
    source_text: str,
    *,
    source_path: Path | None = None,
):
    try:
        program = parse(source_text)
    except (LexerError, ParserError) as error:
        if source_path is not None:
            error.source_path = source_path
        raise
    if program.imports:
        declaration = program.imports[0]
        raise ModuleError(
            "KS5701",
            "Native reality v1 has no authenticated object-edge table; "
            "imports fail closed instead of using filename fallback.",
            declaration.location,
        )
    return program


def _encode(reality: NativeReality, *, seal_key: bytes) -> bytes:
    key = _seal_key(seal_key)
    project_id = _require_bytes(reality.project_id, _ID_BYTES, "project_id")
    object_id = _require_bytes(reality.root_object_id, _ID_BYTES, "root_object_id")
    policy = _require_bytes(reality.policy_digest, _DIGEST_BYTES, "policy_digest")
    artifact = _require_bytes(
        reality.artifact_digest, _DIGEST_BYTES, "artifact_digest"
    )
    alias = _require_bytes(reality.epoch_alias, _ALIAS_BYTES, "epoch_alias")
    if (
        not isinstance(reality.epoch, int)
        or isinstance(reality.epoch, bool)
        or reality.epoch < 1
    ):
        _fail("epoch must be a positive integer")
    if reality.epoch > (1 << 64) - 1:
        _fail("epoch exceeds uint64")
    body = _HEADER.pack(
        REALITY_MAGIC,
        REALITY_SCHEMA_VERSION,
        project_id,
        object_id,
        policy,
        artifact,
        reality.epoch,
        alias,
    )
    return body + hmac.new(key, body, hashlib.sha256).digest()


def _decode(payload: bytes, *, seal_key: bytes) -> NativeReality:
    key = _seal_key(seal_key)
    if not isinstance(payload, bytes) or len(payload) != REALITY_ENVELOPE_BYTES:
        _fail(f"reality envelope must be exactly {REALITY_ENVELOPE_BYTES} bytes")
    body, seal = payload[:-_DIGEST_BYTES], payload[-_DIGEST_BYTES:]
    expected_seal = hmac.new(key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_seal, seal):
        _fail("reality envelope authentication failed")
    (
        magic,
        version,
        project_id,
        object_id,
        policy,
        artifact,
        epoch,
        alias,
    ) = _HEADER.unpack(body)
    if magic != REALITY_MAGIC:
        _fail("reality magic mismatch")
    if version != REALITY_SCHEMA_VERSION:
        _fail(f"unsupported reality schema version: {version}")
    return NativeReality(
        project_id=_require_bytes(project_id, _ID_BYTES, "project_id"),
        root_object_id=_require_bytes(object_id, _ID_BYTES, "root_object_id"),
        policy_digest=_require_bytes(policy, _DIGEST_BYTES, "policy_digest"),
        artifact_digest=_require_bytes(artifact, _DIGEST_BYTES, "artifact_digest"),
        epoch=epoch,
        epoch_alias=_require_bytes(alias, _ALIAS_BYTES, "epoch_alias"),
    )


def _directory_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_directory_path(path: Path, label: str) -> int:
    try:
        before = path.lstat()
    except OSError as error:
        raise NativeRealityError(f"{label} unavailable: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        _fail(f"{label} must be a real directory, not a symlink or special file")
    try:
        descriptor = os.open(path, _directory_flags())
    except OSError as error:
        raise NativeRealityError(f"{label} cannot be opened safely: {error}") from error
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISDIR(after.st_mode):
            _fail(f"{label} must resolve to a directory descriptor")
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            _fail(f"{label} changed between inspection and descriptor open")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_directory_at(parent_fd: int, name: str, label: str) -> int:
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as error:
        raise NativeRealityError(f"{label} cannot be opened safely: {error}") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            _fail(f"{label} must be a real directory")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_regular_at(
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
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise NativeRealityError(f"{label} cannot be opened safely: {error}") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            _fail(f"{label} must be a regular non-symlink file")
        if info.st_size > max_bytes:
            _fail(f"{label} exceeds the {max_bytes}-byte limit")
        if exact_bytes is not None and info.st_size != exact_bytes:
            _fail(f"{label} must be exactly {exact_bytes} bytes")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            _fail(f"{label} exceeds the {max_bytes}-byte limit")
        if exact_bytes is not None and len(payload) != exact_bytes:
            _fail(f"{label} length changed while reading")
        after = os.fstat(descriptor)
        if (info.st_dev, info.st_ino, info.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            _fail(f"{label} changed while being read")
        return payload
    finally:
        os.close(descriptor)


def _write_exclusive_at(directory_fd: int, name: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                _fail(f"failed to write opaque object {name}")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unlink_at(directory_fd: int, name: str) -> None:
    os.unlink(name, dir_fd=directory_fd)


def _replace_sealed_at(reality_fd: int, payload: bytes) -> None:
    temporary = ".reality-" + secrets.token_hex(16)
    try:
        _write_exclusive_at(reality_fd, temporary, payload)
        os.rename(
            temporary,
            REALITY_FILE_NAME,
            src_dir_fd=reality_fd,
            dst_dir_fd=reality_fd,
        )
        os.fsync(reality_fd)
    finally:
        try:
            _unlink_at(reality_fd, temporary)
        except FileNotFoundError:
            pass


def _fresh_nonzero(size: int) -> bytes:
    while True:
        value = secrets.token_bytes(size)
        if any(value):
            return value


def _layout(root: Path) -> tuple[Path, Path, Path]:
    reality_root = root / REALITY_DIR_NAME
    return (
        reality_root,
        reality_root / REALITY_FILE_NAME,
        reality_root / MATTER_DIR_NAME,
    )


@contextmanager
def _open_existing_layout(
    root: Path,
) -> Iterator[tuple[int, int, int]]:
    _require_secure_platform()
    root_fd = _open_directory_path(root, "project root")
    reality_fd: int | None = None
    matter_fd: int | None = None
    try:
        reality_fd = _open_directory_at(root_fd, REALITY_DIR_NAME, "reality root")
        matter_fd = _open_directory_at(reality_fd, MATTER_DIR_NAME, "matter root")
        yield root_fd, reality_fd, matter_fd
    finally:
        if matter_fd is not None:
            os.close(matter_fd)
        if reality_fd is not None:
            os.close(reality_fd)
        os.close(root_fd)


@contextmanager
def _exclusive_reality_transition(reality_fd: int) -> Iterator[None]:
    assert fcntl is not None
    fcntl.flock(reality_fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(reality_fd, fcntl.LOCK_UN)


def _validate_context(
    reality: NativeReality,
    *,
    expected_project_id: bytes,
    expected_epoch: int,
    expected_policy_digest: bytes,
) -> None:
    expected_project = _require_bytes(
        expected_project_id, _ID_BYTES, "expected_project_id"
    )
    if not hmac.compare_digest(reality.project_id, expected_project):
        _fail("reality project id does not match the trusted project context")
    if (
        not isinstance(expected_epoch, int)
        or isinstance(expected_epoch, bool)
        or expected_epoch < 1
        or reality.epoch != expected_epoch
    ):
        _fail("reality epoch does not match the trusted temporal context")
    expected_policy = _require_bytes(
        expected_policy_digest, _DIGEST_BYTES, "expected_policy_digest"
    )
    if not hmac.compare_digest(reality.policy_digest, expected_policy):
        _fail("reality policy digest does not match the local policy")


def _load_from_handles(
    root: Path,
    reality_fd: int,
    matter_fd: int,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    expected_policy_digest: bytes = POLICY_DIGEST_V1,
) -> NativeRealityProject:
    reality = _decode(
        _read_regular_at(
            reality_fd,
            REALITY_FILE_NAME,
            label="reality envelope",
            max_bytes=REALITY_ENVELOPE_BYTES,
            exact_bytes=REALITY_ENVELOPE_BYTES,
        ),
        seal_key=seal_key,
    )
    _validate_context(
        reality,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
        expected_policy_digest=expected_policy_digest,
    )
    alias_text = reality.epoch_alias_text
    if len(alias_text) != 32 or alias_text.lower() != alias_text:
        _fail("epoch alias is not canonical lowercase 128-bit hex")
    source_bytes = _read_regular_at(
        matter_fd,
        alias_text,
        label="canonical source object",
        max_bytes=MAX_SOURCE_BYTES,
    )
    if not hmac.compare_digest(
        hashlib.sha256(source_bytes).digest(),
        reality.artifact_digest,
    ):
        _fail("canonical source object hash mismatch")
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeError as error:
        raise NativeRealityError(
            f"canonical source object is not UTF-8: {error}"
        ) from error
    reality_root, reality_path, matter_root = _layout(root)
    del reality_root
    return NativeRealityProject(
        root=root,
        reality_path=reality_path,
        matter_root=matter_root,
        reality=reality,
        source_path=matter_root / alias_text,
        source_text=source_text,
        source_bytes=source_bytes,
    )


def is_native_reality_project(path: str | Path) -> bool:
    root = _absolute_no_symlink_resolution(path)
    try:
        with _open_existing_layout(root) as (_, reality_fd, _):
            _read_regular_at(
                reality_fd,
                REALITY_FILE_NAME,
                label="reality envelope",
                max_bytes=REALITY_ENVELOPE_BYTES,
                exact_bytes=REALITY_ENVELOPE_BYTES,
            )
    except (NativeRealityError, OSError):
        return False
    return True


def _safe_remove_created_root(root: Path, identity: tuple[int, int]) -> None:
    try:
        info = root.lstat()
        if (
            stat.S_ISDIR(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and (info.st_dev, info.st_ino) == identity
        ):
            root.rmdir()
    except OSError:
        pass


def create_native_reality_project(
    destination: str | Path,
    *,
    seal_key: bytes,
    source_text: str = 'fn main() {\n    println("Hello from Koschei reality")\n}\n',
) -> NativeRealityProject:
    _require_secure_platform()
    _seal_key(seal_key)
    source_bytes = _source_bytes(source_text)
    _parse_single_object_source(source_text)

    root = _absolute_no_symlink_resolution(destination)
    existed = root.exists() or root.is_symlink()
    if not existed:
        root.mkdir(parents=True, mode=0o700)

    root_fd: int | None = None
    reality_fd: int | None = None
    matter_fd: int | None = None
    alias_text: str | None = None
    created_reality = False
    root_identity: tuple[int, int] | None = None
    success = False
    try:
        root_fd = _open_directory_path(root, "project root")
        root_info = os.fstat(root_fd)
        root_identity = (root_info.st_dev, root_info.st_ino)
        if os.listdir(root_fd):
            _fail(f"destination is not empty: {root}")

        os.mkdir(REALITY_DIR_NAME, 0o700, dir_fd=root_fd)
        created_reality = True
        reality_fd = _open_directory_at(root_fd, REALITY_DIR_NAME, "reality root")
        os.mkdir(MATTER_DIR_NAME, 0o700, dir_fd=reality_fd)
        matter_fd = _open_directory_at(reality_fd, MATTER_DIR_NAME, "matter root")

        alias = _fresh_nonzero(_ALIAS_BYTES)
        alias_text = alias.hex()
        artifact = hashlib.sha256(source_bytes).digest()
        reality = NativeReality(
            project_id=_fresh_nonzero(_ID_BYTES),
            root_object_id=_fresh_nonzero(_ID_BYTES),
            policy_digest=POLICY_DIGEST_V1,
            artifact_digest=artifact,
            epoch=1,
            epoch_alias=alias,
        )
        _write_exclusive_at(matter_fd, alias_text, source_bytes)
        os.fsync(matter_fd)
        _write_exclusive_at(
            reality_fd,
            REALITY_FILE_NAME,
            _encode(reality, seal_key=seal_key),
        )
        os.fsync(reality_fd)
        os.fsync(root_fd)
        success = True
    finally:
        if not success:
            if matter_fd is not None and alias_text is not None:
                try:
                    _unlink_at(matter_fd, alias_text)
                except OSError:
                    pass
            if reality_fd is not None:
                try:
                    _unlink_at(reality_fd, REALITY_FILE_NAME)
                except OSError:
                    pass
            if matter_fd is not None:
                os.close(matter_fd)
                matter_fd = None
            if reality_fd is not None:
                try:
                    os.rmdir(MATTER_DIR_NAME, dir_fd=reality_fd)
                except OSError:
                    pass
                os.close(reality_fd)
                reality_fd = None
            if root_fd is not None and created_reality:
                try:
                    os.rmdir(REALITY_DIR_NAME, dir_fd=root_fd)
                except OSError:
                    pass
        if matter_fd is not None:
            os.close(matter_fd)
        if reality_fd is not None:
            os.close(reality_fd)
        if root_fd is not None:
            os.close(root_fd)

    if not success:
        if not existed and root_identity is not None:
            _safe_remove_created_root(root, root_identity)
        _fail("native reality project creation failed")

    return load_native_reality_project(
        root,
        seal_key=seal_key,
        expected_project_id=reality.project_id,
        expected_epoch=1,
    )


def load_native_reality_project(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    expected_policy_digest: bytes = POLICY_DIGEST_V1,
) -> NativeRealityProject:
    _require_secure_platform()
    _seal_key(seal_key)
    root = _absolute_no_symlink_resolution(path)
    with _open_existing_layout(root) as (_, reality_fd, matter_fd):
        return _load_from_handles(
            root,
            reality_fd,
            matter_fd,
            seal_key=seal_key,
            expected_project_id=expected_project_id,
            expected_epoch=expected_epoch,
            expected_policy_digest=expected_policy_digest,
        )


def load_native_reality_graph(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
) -> ModuleGraph:
    project = load_native_reality_project(
        path,
        seal_key=seal_key,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
    )
    program = _parse_single_object_source(
        project.source_text,
        source_path=project.source_path,
    )
    key = "koschei-object:" + project.reality.root_object_id_hex
    module = Module(
        name=project.reality.root_object_id_hex,
        path=project.source_path,
        program=program,
    )
    return ModuleGraph(root=key, modules={key: module})


def _fresh_alias_write(
    matter_fd: int,
    *,
    previous_alias: bytes,
    source_bytes: bytes,
) -> tuple[bytes, str]:
    for _ in range(16):
        alias = _fresh_nonzero(_ALIAS_BYTES)
        if alias == previous_alias:
            continue
        alias_text = alias.hex()
        try:
            _write_exclusive_at(matter_fd, alias_text, source_bytes)
        except FileExistsError:
            continue
        os.fsync(matter_fd)
        return alias, alias_text
    _fail("unable to allocate a fresh opaque source alias")


def _transition_reality(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    replacement_source_bytes: bytes | None,
    replacement_artifact_digest: bytes | None,
) -> NativeRealityProject:
    _require_secure_platform()
    _seal_key(seal_key)
    root = _absolute_no_symlink_resolution(path)
    with _open_existing_layout(root) as (_, reality_fd, matter_fd):
        with _exclusive_reality_transition(reality_fd):
            current = _load_from_handles(
                root,
                reality_fd,
                matter_fd,
                seal_key=seal_key,
                expected_project_id=expected_project_id,
                expected_epoch=expected_epoch,
            )
            reality = current.reality
            if reality.epoch >= (1 << 64) - 1:
                _fail("epoch counter exhausted")

            source_bytes = (
                current.source_bytes
                if replacement_source_bytes is None
                else replacement_source_bytes
            )
            artifact_digest = (
                reality.artifact_digest
                if replacement_artifact_digest is None
                else _require_bytes(
                    replacement_artifact_digest,
                    _DIGEST_BYTES,
                    "replacement_artifact_digest",
                )
            )
            if not hmac.compare_digest(
                hashlib.sha256(source_bytes).digest(),
                artifact_digest,
            ):
                _fail("replacement artifact digest does not match source bytes")

            new_alias, new_alias_text = _fresh_alias_write(
                matter_fd,
                previous_alias=reality.epoch_alias,
                source_bytes=source_bytes,
            )
            next_reality = NativeReality(
                project_id=reality.project_id,
                root_object_id=reality.root_object_id,
                policy_digest=reality.policy_digest,
                artifact_digest=artifact_digest,
                epoch=reality.epoch + 1,
                epoch_alias=new_alias,
            )
            switched = False
            try:
                _replace_sealed_at(
                    reality_fd,
                    _encode(next_reality, seal_key=seal_key),
                )
                switched = True
            finally:
                if not switched:
                    try:
                        _unlink_at(matter_fd, new_alias_text)
                        os.fsync(matter_fd)
                    except OSError:
                        pass

            try:
                _unlink_at(matter_fd, reality.epoch_alias_text)
                os.fsync(matter_fd)
            except OSError:
                pass

            return _load_from_handles(
                root,
                reality_fd,
                matter_fd,
                seal_key=seal_key,
                expected_project_id=reality.project_id,
                expected_epoch=reality.epoch + 1,
            )


def advance_native_reality_source(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    source_text: str,
) -> NativeRealityProject:
    """Authenticate an edit and advance source identity as one new epoch."""

    source_bytes = _source_bytes(source_text)
    _parse_single_object_source(source_text)
    return _transition_reality(
        path,
        seal_key=seal_key,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
        replacement_source_bytes=source_bytes,
        replacement_artifact_digest=hashlib.sha256(source_bytes).digest(),
    )


def rotate_native_reality_epoch(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
) -> NativeRealityProject:
    return _transition_reality(
        path,
        seal_key=seal_key,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
        replacement_source_bytes=None,
        replacement_artifact_digest=None,
    )
