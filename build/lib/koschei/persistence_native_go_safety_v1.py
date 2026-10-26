"""Fail-closed target-shape hardening for Linux native persistence v1.

A metadata probe must not perform a blocking/side-effectful normal read-open of a
FIFO/device just to discover its type. Linux O_PATH gives a descriptor suitable
for fstat without opening the object for data I/O. O_NOFOLLOW keeps a final
symlink as the inspected object instead of following it.

The real load open also uses O_NONBLOCK so a race that swaps a previously regular
file for a FIFO cannot wedge the runtime before fstat rejects the new descriptor.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import persistence_native_go_v1 as _native

_INSTALLED = False

_OLD_CONSTANTS = '''const ksPersistMaxBytes int64 = 16 * 1024 * 1024
const ksPersistMaxDeadlineMs int64 = 120000
const ksPersistChunkBytes int = 64 * 1024'''
_NEW_CONSTANTS = '''const ksPersistMaxBytes int64 = 16 * 1024 * 1024
const ksPersistMaxDeadlineMs int64 = 120000
const ksPersistChunkBytes int = 64 * 1024
// Linux O_PATH. Native persistence is already Linux-gated before generation.
const ksPersistOPath int = 0x200000'''

_OLD_SHAPE_OPEN = '''\tfd, err := syscall.Openat(
\t\tparentFD,
\t\tname,
\t\tsyscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
\t\t0,
\t)'''
_NEW_SHAPE_OPEN = '''\tfd, err := syscall.Openat(
\t\tparentFD,
\t\tname,
\t\tksPersistOPath|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
\t\t0,
\t)'''

_OLD_LOAD_OPEN = '''\tfd, err := syscall.Openat(
\t\tparentFD,
\t\tcapability.name,
\t\tsyscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
\t\t0,
\t)'''
_NEW_LOAD_OPEN = '''\tfd, err := syscall.Openat(
\t\tparentFD,
\t\tcapability.name,
\t\tsyscall.O_RDONLY|syscall.O_NONBLOCK|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
\t\t0,
\t)'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new in source:
        return source
    raise RuntimeError(f"Native persistence safety marker changed at {label}; fail-closed.")


def _harden(source: str) -> str:
    source = _replace_once(source, _OLD_CONSTANTS, _NEW_CONSTANTS, "O_PATH constant")
    source = _replace_once(source, _OLD_SHAPE_OPEN, _NEW_SHAPE_OPEN, "shape probe")
    source = _replace_once(source, _OLD_LOAD_OPEN, _NEW_LOAD_OPEN, "load race guard")
    return source


def install_persistence_native_go_safety_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _native._GO_PERSIST_HELPERS = _harden(_native._GO_PERSIST_HELPERS)
    _codegen.CAPABILITY_RUNTIME = _harden(_codegen.CAPABILITY_RUNTIME)
    _INSTALLED = True
