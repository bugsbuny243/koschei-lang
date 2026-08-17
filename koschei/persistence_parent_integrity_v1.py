"""Parent-directory integrity guard for exact-object persistence v1.

The atomic temp+rename protocol assumes another Unix identity cannot freely remove
or replace names in the anchored parent directory. A group/world-writable parent
without the sticky bit violates that assumption: another authorized OS user could
observe the random temp name and swap directory entries before the visibility
commit.

Sticky shared directories (for example a correctly configured /tmp) remain
admissible because Unix sticky semantics restrict deletion/rename of entries owned
by another identity. Same-UID hostile processes remain outside this v1 guarantee
and are documented separately; Unix mode bits cannot distinguish them.
"""

from __future__ import annotations

import os
import stat

from . import bounded_persistence_v1 as _persist
from .persistence_authority_v1 import PersistCaps

_INSTALLED = False
_ORIGINAL_PARENT_DUPLICATE = None


def _parent_duplicate(
    capability: PersistCaps,
):
    parent_fd, failure = _ORIGINAL_PARENT_DUPLICATE(capability)
    if failure is not None or parent_fd is None:
        return parent_fd, failure

    try:
        info = os.fstat(parent_fd)
    except OSError as error:
        os.close(parent_fd)
        return None, _persist._io_error(
            f"persistence parent metadata read failed: {error}"
        )

    if not stat.S_ISDIR(info.st_mode):
        os.close(parent_fd)
        return None, _persist._contract_error(
            "persistence parent descriptor is no longer a directory"
        )

    shared_write = bool(info.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
    sticky = bool(info.st_mode & stat.S_ISVTX)
    if shared_write and not sticky:
        os.close(parent_fd)
        return None, _persist._contract_error(
            "persistence parent is group/world-writable without sticky-bit entry protection"
        )

    return parent_fd, None


def install_persistence_parent_integrity_v1() -> None:
    global _INSTALLED, _ORIGINAL_PARENT_DUPLICATE
    if _INSTALLED:
        return

    _ORIGINAL_PARENT_DUPLICATE = _persist._parent_duplicate
    _persist._parent_duplicate = _parent_duplicate
    _INSTALLED = True
