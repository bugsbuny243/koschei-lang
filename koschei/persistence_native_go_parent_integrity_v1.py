"""Linux native-Go parity for persistence parent-directory integrity v1."""

from __future__ import annotations

from . import codegen_go as _codegen
from . import persistence_native_go_v1 as _native

_INSTALLED = False

_OLD_DUP_TAIL = '''\tfd, err := syscall.Dup(capability.parentFD)
\tif err != nil {
\t\treturn -1, ksPersistIO("persistence parent descriptor duplication failed: " + err.Error())
\t}
\treturn fd, nil
}'''

_NEW_DUP_TAIL = '''\tfd, err := syscall.Dup(capability.parentFD)
\tif err != nil {
\t\treturn -1, ksPersistIO("persistence parent descriptor duplication failed: " + err.Error())
\t}
\tvar parentInfo syscall.Stat_t
\tif err := syscall.Fstat(fd, &parentInfo); err != nil {
\t\t_ = syscall.Close(fd)
\t\treturn -1, ksPersistIO("persistence parent metadata read failed: " + err.Error())
\t}
\tif parentInfo.Mode&syscall.S_IFMT != syscall.S_IFDIR {
\t\t_ = syscall.Close(fd)
\t\treturn -1, ksPersistContract("persistence parent descriptor is no longer a directory")
\t}
\tsharedWrite := parentInfo.Mode&0o022 != 0
\tsticky := parentInfo.Mode&0o1000 != 0
\tif sharedWrite && !sticky {
\t\t_ = syscall.Close(fd)
\t\treturn -1, ksPersistContract("persistence parent is group/world-writable without sticky-bit entry protection")
\t}
\treturn fd, nil
}'''


def _harden(source: str) -> str:
    if _OLD_DUP_TAIL in source:
        return source.replace(_OLD_DUP_TAIL, _NEW_DUP_TAIL, 1)
    if _NEW_DUP_TAIL in source:
        return source
    raise RuntimeError(
        "Native persistence parent-integrity dispatcher changed; fail-closed."
    )


def install_persistence_native_go_parent_integrity_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _native._GO_PERSIST_HELPERS = _harden(_native._GO_PERSIST_HELPERS)
    _codegen.CAPABILITY_RUNTIME = _harden(_codegen.CAPABILITY_RUNTIME)
    _INSTALLED = True
