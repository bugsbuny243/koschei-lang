"""Second adversarial hardening round for Object Space v1.

Closes two availability/authority-continuity gaps found after the first Railway
red-team pass:

* the public k1 path must still name the admitted k1 descriptor at the exact k0
  authority-switch point; and
* opaque-cell enumeration is streaming and bounded, so an attacker cannot force
  an unbounded Python list of filesystem names before authority validation.
"""

from __future__ import annotations

import os
import stat

from . import object_space_v1 as _space
from . import object_space_adversarial_guard_v1 as _guard

_INSTALLED = False
_ORIGINAL_COMMIT_ROOT_SWITCH = None

# Authoritative objects are capped at MAX_OBJECTS. A bounded stale/cover-cell
# allowance keeps cleanup-failure semantics possible without allowing unbounded
# directory reconnaissance cost inside the trusted runtime.
MAX_INERT_PHYSICAL_CELLS_V1 = 1024
MAX_PHYSICAL_CELLS_V1 = _space.MAX_OBJECTS + MAX_INERT_PHYSICAL_CELLS_V1


def _bounded_strict_list_opaque(directory_fd: int) -> tuple[str, ...]:
    names: list[str] = []
    try:
        iterator = os.scandir(directory_fd)
    except (OSError, TypeError) as error:
        raise _space.ObjectSpaceError(
            f"k1 cannot be enumerated through its admitted descriptor: {error}"
        ) from error
    with iterator:
        for entry in iterator:
            name = entry.name
            if _space._LOCATOR_RE.fullmatch(name) is None:
                _space._fail("k1 contains a non-opaque physical name")
            names.append(name)
            if len(names) > MAX_PHYSICAL_CELLS_V1:
                _space._fail(
                    f"k1 physical cell budget exceeds {MAX_PHYSICAL_CELLS_V1}"
                )
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
    return tuple(sorted(names))


def _store_path_matches_fd(root_fd: int, store_fd: int) -> bool:
    try:
        path_info = os.stat(
            _space.OBJECT_STORE_NAME,
            dir_fd=root_fd,
            follow_symlinks=False,
        )
        descriptor_info = os.fstat(store_fd)
    except OSError:
        return False
    return (
        stat.S_ISDIR(path_info.st_mode)
        and not stat.S_ISLNK(path_info.st_mode)
        and (path_info.st_dev, path_info.st_ino)
        == (descriptor_info.st_dev, descriptor_info.st_ino)
    )


def _identity_checked_commit_root_switch(
    *, pending: str, store_fd: int, root_fd: int
) -> None:
    if not _store_path_matches_fd(root_fd, store_fd):
        _space._fail("k1 path identity changed before k0 authority switch")
    assert _ORIGINAL_COMMIT_ROOT_SWITCH is not None
    _ORIGINAL_COMMIT_ROOT_SWITCH(
        pending=pending,
        store_fd=store_fd,
        root_fd=root_fd,
    )


def install_object_space_redteam_round2_v1() -> None:
    global _INSTALLED, _ORIGINAL_COMMIT_ROOT_SWITCH
    if _INSTALLED:
        return
    _ORIGINAL_COMMIT_ROOT_SWITCH = _guard._commit_root_switch
    _guard._commit_root_switch = _identity_checked_commit_root_switch
    _space._list_opaque = _bounded_strict_list_opaque
    _INSTALLED = True
