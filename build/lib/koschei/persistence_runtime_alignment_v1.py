"""Platform feature alignment for bounded persistence v1.

CPython exposes ``os.replace(..., src_dir_fd=, dst_dir_fd=)`` on POSIX but does
not consistently list os.replace in ``os.supports_dir_fd``. Persistence must test
the actual callable contract rather than incorrectly disabling a safe backend.
"""

from __future__ import annotations

import inspect
import os

from . import bounded_persistence_v1 as _persist

_INSTALLED = False


def _replace_has_dir_fd_contract() -> bool:
    try:
        parameters = inspect.signature(os.replace).parameters
    except (TypeError, ValueError):
        return False
    return "src_dir_fd" in parameters and "dst_dir_fd" in parameters


def install_persistence_runtime_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _persist._PERSIST_FD_SUPPORTED = bool(
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and _replace_has_dir_fd_contract()
    )
    _INSTALLED = True
