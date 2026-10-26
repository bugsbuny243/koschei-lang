"""Red-team routing guard for Object Space ``check``.

A symlink whose target presents k0/k1 is still an Object Space *routing hint*.
The trusted broker will then perform real admission and reject the symlink root.
It must never fall through to the legacy .ks/project resolver merely because the
outer path component is a symlink.

Following the symlink here grants no authority; this function only chooses which
fail-closed admission path receives the request.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat

from . import object_space_check_v1 as _check
from .object_space_v1 import OBJECT_STORE_NAME, ROOT_CAPSULE_NAME

_INSTALLED = False


def _strict_object_space_routing_hint(path: str | Path) -> bool:
    root = _check._absolute_without_resolving_symlinks(path)
    try:
        info = root.lstat()
    except OSError:
        return False

    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
        return False

    # lexists deliberately treats malformed/symlink children as presence. The
    # broker, not this hint, decides whether any of them are admissible.
    try:
        return os.path.lexists(root / ROOT_CAPSULE_NAME) or os.path.lexists(
            root / OBJECT_STORE_NAME
        )
    except OSError:
        return False


def install_object_space_check_adversarial_guard_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _check._looks_like_object_space = _strict_object_space_routing_hint
    _INSTALLED = True
