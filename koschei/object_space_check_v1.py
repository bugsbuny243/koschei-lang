"""Object Space integration for the compiler ``check`` command only.

Raw crypto keys, temporal keys and handles are intentionally absent from the CLI.
An embedding Trust Plane/session broker must install a scoped opener in the current
context. The opener is responsible for performing the real Object Space load and
returning the authenticated ``ObjectSpaceProject``.

This slice does not alter run/mir/caps/build. They remain on the legacy source
resolver until separately designed, tested and attacked.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import stat
from typing import Callable, Iterator

from . import cli as _cli
from .mir import require_mir
from .object_space_graph_v1 import check_object_space_graph
from .object_space_v1 import ObjectSpaceProject, ROOT_CAPSULE_NAME, OBJECT_STORE_NAME


class ObjectSpaceCheckSessionError(ValueError):
    pass


ObjectSpaceProjectOpener = Callable[[Path], ObjectSpaceProject]
_SESSION_OPENER: ContextVar[ObjectSpaceProjectOpener | None] = ContextVar(
    "koschei_object_space_check_session_opener",
    default=None,
)
_INSTALLED = False
_ORIGINAL_COMMAND_CHECK = None


def _absolute_without_resolving_symlinks(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _looks_like_object_space(path: str | Path) -> bool:
    """Cheap routing hint only; all security admission belongs to the broker.

    Symlinks/special files deliberately count as a candidate so malformed Object
    Space roots cannot fall through to the legacy project resolver.
    """

    root = _absolute_without_resolving_symlinks(path)
    try:
        root_info = root.lstat()
    except OSError:
        return False
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        return False
    return os.path.lexists(root / ROOT_CAPSULE_NAME) or os.path.lexists(
        root / OBJECT_STORE_NAME
    )


@contextmanager
def object_space_check_session(opener: ObjectSpaceProjectOpener) -> Iterator[None]:
    if not callable(opener):
        raise ObjectSpaceCheckSessionError("Object Space check opener must be callable")
    token = _SESSION_OPENER.set(opener)
    try:
        yield
    finally:
        _SESSION_OPENER.reset(token)


def _open_scoped_project(path: str | Path) -> ObjectSpaceProject:
    opener = _SESSION_OPENER.get()
    if opener is None:
        raise ObjectSpaceCheckSessionError(
            "Object Space check requires a trusted session broker; raw keys/handles "
            "are not accepted by the CLI"
        )
    requested = _absolute_without_resolving_symlinks(path)
    project = opener(requested)
    if not isinstance(project, ObjectSpaceProject):
        raise ObjectSpaceCheckSessionError(
            "Object Space session broker returned a non-canonical project value"
        )
    returned = _absolute_without_resolving_symlinks(project.root)
    if returned != requested:
        raise ObjectSpaceCheckSessionError(
            "Object Space session broker returned a different project root"
        )
    return project


def _object_space_command_check(path: str, as_json: bool, locale: str) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_CHECK is not None
        return _ORIGINAL_COMMAND_CHECK(path, as_json, locale)

    project = _open_scoped_project(path)
    graph, report = check_object_space_graph(project)
    module_count = len(graph.modules)
    sealed_mir = require_mir(graph)

    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    # Do not serialize a semantic entry filename: Object Space has none.
                    "source": "<object-space>",
                    "functions": report.functions,
                    "variables": report.variables,
                    "capability_values": report.capability_values,
                    "modules": module_count,
                    "mir_version": sealed_mir.version,
                    "mir_fingerprint": sealed_mir.fingerprint,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if locale == "en":
        suffix = f", {module_count} objects" if module_count > 1 else ""
        print(
            f"KOSCHEI CHECK: PASS ({report.functions} functions, "
            f"{report.variables} variables, "
            f"{report.capability_values} capability values{suffix})"
        )
    else:
        suffix = f", {module_count} nesne" if module_count > 1 else ""
        print(
            f"KOSCHEI CHECK: PASS ({report.functions} fonksiyon, "
            f"{report.variables} değişken, "
            f"{report.capability_values} capability değeri{suffix})"
        )
    return 0


def install_object_space_check_v1() -> None:
    global _INSTALLED, _ORIGINAL_COMMAND_CHECK
    if _INSTALLED:
        return
    _ORIGINAL_COMMAND_CHECK = _cli.command_check
    _cli.command_check = _object_space_command_check
    _INSTALLED = True
