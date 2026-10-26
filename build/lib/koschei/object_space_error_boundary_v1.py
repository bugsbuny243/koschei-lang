"""Normalize shared Native Reality filesystem failures into Object Space errors.

Object Space reuses descriptor-safe filesystem primitives from Native Reality, but
those implementation details must not leak a second public exception family.
The wrapper preserves the original exception as ``__cause__`` and changes only
shared NativeRealityError failures; ObjectSpaceError and unrelated programming or
provider exceptions keep their original semantics.
"""

from __future__ import annotations

from functools import wraps

from . import object_space_v1 as _space
from .native_reality_v1 import NativeRealityError

_INSTALLED = False


def _normalize(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except _space.ObjectSpaceError:
            raise
        except NativeRealityError as error:
            raise _space.ObjectSpaceError(str(error)) from error

    return wrapped


def install_object_space_error_boundary_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # These helpers are imported from Native Reality solely as implementation
    # primitives. Their public failures belong to the Object Space API once used
    # here. Do not wrap crypto/provider exceptions or arbitrary OSError injected
    # at explicit commit seams: those carry distinct commit-state meaning.
    for name in (
        "_require_secure_platform",
        "_open_directory_path",
        "_open_directory_at",
        "_read_regular_at",
        "_write_exclusive_at",
    ):
        setattr(_space, name, _normalize(getattr(_space, name)))

    _INSTALLED = True
