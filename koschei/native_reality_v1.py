"""Koschei-native object-identity project reality v1.

This is the first project format that does not use a human-readable entry path,
package manifest, or semantic source filename as authority.

v1 intentionally admits one canonical root object and no imports. Multi-object
projects must use an authenticated object-edge format in a later revision; v1
fails closed instead of falling back to sibling filenames.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import shutil
import stat
import struct

from .ast_nodes import SourceLocation
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
    b"no-implicit-import-fallback"
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


def _fail(message: str) -> None:
    raise NativeRealityError(message)


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
    # Path.resolve() follows the final project-root symlink before we can reject
    # it. absolute() preserves the link itself for lstat-based admission checks.
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
        _fail(
            f"reality envelope must be exactly {REALITY_ENVELOPE_BYTES} bytes"
        )
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


def _ensure_real_directory(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise NativeRealityError(f"{label} unavailable: {error}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(
            f"{label} must be a real directory, "
            "not a symlink or special file"
        )


def _read_regular_nofollow(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    exact_bytes: int | None = None,
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        before = path.lstat()
    except OSError as error:
        raise NativeRealityError(
            f"{label} cannot be inspected safely: {error}"
        ) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _fail(f"{label} must be a regular non-symlink file")
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise NativeRealityError(
            f"{label} cannot be opened safely: {error}"
        ) from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            _fail(f"{label} must be a regular file")
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
            _fail(f"{label} changed between inspection and open")
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


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                _fail(f"failed to write {path.name}")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_sealed(path: Path, payload: bytes) -> None:
    parent = path.parent
    temporary = parent / (".reality-" + secrets.token_hex(16))
    try:
        _write_exclusive(temporary, payload)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
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


def is_native_reality_project(path: str | Path) -> bool:
    requested = _absolute_no_symlink_resolution(path)
    try:
        _ensure_real_directory(requested, "project root")
        reality_root, reality_path, matter_root = _layout(requested)
        _ensure_real_directory(reality_root, "reality root")
        _ensure_real_directory(matter_root, "matter root")
        reality_info = reality_path.lstat()
    except NativeRealityError:
        return False
    except OSError:
        return False
    return stat.S_ISREG(reality_info.st_mode) and not stat.S_ISLNK(
        reality_info.st_mode
    )


def create_native_reality_project(
    destination: str | Path,
    *,
    seal_key: bytes,
    source_text: str = 'fn main() {\n    println("Hello from Koschei reality")\n}\n',
) -> NativeRealityProject:
    _seal_key(seal_key)
    source_bytes = _source_bytes(source_text)
    # Reject known-unbuildable v1 realities before creating any filesystem state.
    _parse_single_object_source(source_text)

    root = _absolute_no_symlink_resolution(destination)
    existed = root.exists() or root.is_symlink()
    if existed:
        _ensure_real_directory(root, "project root")
        if any(root.iterdir()):
            _fail(f"destination is not empty: {root}")

    created_root = False
    try:
        if not existed:
            root.mkdir(parents=True, mode=0o700)
            created_root = True
        reality_root, reality_path, matter_root = _layout(root)
        reality_root.mkdir(mode=0o700)
        matter_root.mkdir(mode=0o700)
        alias = _fresh_nonzero(_ALIAS_BYTES)
        source_path = matter_root / alias.hex()
        artifact = hashlib.sha256(source_bytes).digest()
        reality = NativeReality(
            project_id=_fresh_nonzero(_ID_BYTES),
            root_object_id=_fresh_nonzero(_ID_BYTES),
            policy_digest=POLICY_DIGEST_V1,
            artifact_digest=artifact,
            epoch=1,
            epoch_alias=alias,
        )
        _write_exclusive(source_path, source_bytes)
        _write_exclusive(
            reality_path,
            _encode(reality, seal_key=seal_key),
        )
        return load_native_reality_project(
            root,
            seal_key=seal_key,
            expected_project_id=reality.project_id,
            expected_epoch=1,
        )
    except Exception:
        if created_root:
            shutil.rmtree(root, ignore_errors=True)
        raise


def load_native_reality_project(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
    expected_policy_digest: bytes = POLICY_DIGEST_V1,
) -> NativeRealityProject:
    _seal_key(seal_key)
    root = _absolute_no_symlink_resolution(path)
    _ensure_real_directory(root, "project root")
    reality_root, reality_path, matter_root = _layout(root)
    _ensure_real_directory(reality_root, "reality root")
    _ensure_real_directory(matter_root, "matter root")
    reality = _decode(
        _read_regular_nofollow(
            reality_path,
            label="reality envelope",
            max_bytes=REALITY_ENVELOPE_BYTES,
            exact_bytes=REALITY_ENVELOPE_BYTES,
        ),
        seal_key=seal_key,
    )
    expected_project = _require_bytes(
        expected_project_id, _ID_BYTES, "expected_project_id"
    )
    if not hmac.compare_digest(reality.project_id, expected_project):
        _fail(
            "reality project id does not match the trusted project context"
        )
    if (
        not isinstance(expected_epoch, int)
        or isinstance(expected_epoch, bool)
        or expected_epoch < 1
        or reality.epoch != expected_epoch
    ):
        _fail(
            "reality epoch does not match the trusted temporal context"
        )
    expected = _require_bytes(
        expected_policy_digest, _DIGEST_BYTES, "expected_policy_digest"
    )
    if not hmac.compare_digest(reality.policy_digest, expected):
        _fail(
            "reality policy digest does not match the local policy"
        )

    alias_text = reality.epoch_alias_text
    if len(alias_text) != 32 or alias_text.lower() != alias_text:
        _fail("epoch alias is not canonical lowercase 128-bit hex")
    source_path = matter_root / alias_text
    source_bytes = _read_regular_nofollow(
        source_path,
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
    return NativeRealityProject(
        root=root,
        reality_path=reality_path,
        matter_root=matter_root,
        reality=reality,
        source_path=source_path,
        source_text=source_text,
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


def _next_alias(current: bytes) -> bytes:
    candidate = _fresh_nonzero(_ALIAS_BYTES)
    while candidate == current:
        candidate = _fresh_nonzero(_ALIAS_BYTES)
    return candidate


def _switch_reality(
    project: NativeRealityProject,
    *,
    seal_key: bytes,
    source_bytes: bytes,
    artifact_digest: bytes,
) -> NativeRealityProject:
    reality = project.reality
    if reality.epoch >= (1 << 64) - 1:
        _fail("epoch counter exhausted")

    new_alias = _next_alias(reality.epoch_alias)
    new_source_path = project.matter_root / new_alias.hex()
    _write_exclusive(new_source_path, source_bytes)
    next_reality = NativeReality(
        project_id=reality.project_id,
        root_object_id=reality.root_object_id,
        policy_digest=reality.policy_digest,
        artifact_digest=artifact_digest,
        epoch=reality.epoch + 1,
        epoch_alias=new_alias,
    )
    try:
        _replace_sealed(
            project.reality_path,
            _encode(next_reality, seal_key=seal_key),
        )
    except Exception:
        try:
            new_source_path.unlink()
        except FileNotFoundError:
            pass
        raise

    # The new envelope is already authoritative. Failure to remove the old
    # unreferenced alias must never roll authority back to stale reality.
    try:
        project.source_path.unlink()
    except OSError:
        pass

    return load_native_reality_project(
        project.root,
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
    """Authenticate an edit and advance source identity as one new epoch.

    Direct writes to the current matter alias are never edits: they invalidate
    the authenticated artifact digest. This operation validates the replacement
    program before any authority switch, writes it under a fresh opaque alias,
    advances the epoch and atomically seals the new reality envelope.
    """

    project = load_native_reality_project(
        path,
        seal_key=seal_key,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
    )
    source_bytes = _source_bytes(source_text)
    # Parse and enforce the single-object boundary before filesystem mutation.
    _parse_single_object_source(source_text)
    artifact_digest = hashlib.sha256(source_bytes).digest()
    return _switch_reality(
        project,
        seal_key=seal_key,
        source_bytes=source_bytes,
        artifact_digest=artifact_digest,
    )


def rotate_native_reality_epoch(
    path: str | Path,
    *,
    seal_key: bytes,
    expected_project_id: bytes,
    expected_epoch: int,
) -> NativeRealityProject:
    project = load_native_reality_project(
        path,
        seal_key=seal_key,
        expected_project_id=expected_project_id,
        expected_epoch=expected_epoch,
    )
    source_bytes = project.source_text.encode("utf-8")
    return _switch_reality(
        project,
        seal_key=seal_key,
        source_bytes=source_bytes,
        artifact_digest=project.reality.artifact_digest,
    )
