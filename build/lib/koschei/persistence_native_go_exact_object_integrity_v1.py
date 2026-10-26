"""Linux native-Go parity for canonical exact-object persistence identity."""

from __future__ import annotations

from . import codegen_go as _codegen
from . import persistence_native_go_v1 as _native

_INSTALLED = False

_OLD_CANONICAL = '''func ksPersistCanonicalPath(raw string) (string, bool) {
\tif strings.IndexByte(raw, 0) >= 0 {
\t\treturn "", false
\t}
\ttext := strings.TrimSpace(raw)
\tif text == "" || !filepath.IsAbs(text) {
\t\treturn "", false
\t}
\tcanonical := filepath.Clean(text)
\tif canonical == string(os.PathSeparator) {
\t\treturn "", false
\t}
\tname := filepath.Base(canonical)
\tif name == "" || name == "." || name == ".." {
\t\treturn "", false
\t}
\treturn canonical, true
}'''

_NEW_CANONICAL = '''func ksPersistCanonicalPath(raw string) (string, bool) {
\tif strings.IndexByte(raw, 0) >= 0 || raw != strings.TrimSpace(raw) {
\t\treturn "", false
\t}
\tif raw == "" || !filepath.IsAbs(raw) {
\t\treturn "", false
\t}
\tcanonical := filepath.Clean(raw)
\tif canonical != raw || canonical == string(os.PathSeparator) {
\t\treturn "", false
\t}
\tname := filepath.Base(canonical)
\tif name == "" || name == "." || name == ".." {
\t\treturn "", false
\t}
\treturn canonical, true
}'''

_OLD_SHAPE_TAIL = '''\tif info.Mode&syscall.S_IFMT != syscall.S_IFREG {
\t\treturn ksPersistContract("persistence target must be a regular file when it exists")
\t}
\treturn nil
}'''
_NEW_SHAPE_TAIL = '''\tif info.Mode&syscall.S_IFMT != syscall.S_IFREG {
\t\treturn ksPersistContract("persistence target must be a regular file when it exists")
\t}
\tif info.Nlink != 1 {
\t\treturn ksPersistContract("persistence target must have exactly one hard-link name")
\t}
\treturn nil
}'''

_OLD_LOAD_STAT = '''\tif info.Mode&syscall.S_IFMT != syscall.S_IFREG {
\t\treturn ksPersistContract("opened persistence target is not a regular file")
\t}
\tif info.Size > capability.policy.maxBytes {'''
_NEW_LOAD_STAT = '''\tif info.Mode&syscall.S_IFMT != syscall.S_IFREG {
\t\treturn ksPersistContract("opened persistence target is not a regular file")
\t}
\tif info.Nlink != 1 {
\t\treturn ksPersistContract("opened persistence target must have exactly one hard-link name")
\t}
\tif info.Size > capability.policy.maxBytes {'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new in source:
        return source
    raise RuntimeError(
        f"Native persistence exact-object marker changed at {label}; fail-closed."
    )


def _harden(source: str) -> str:
    source = _replace_once(source, _OLD_CANONICAL, _NEW_CANONICAL, "canonical path")
    source = _replace_once(source, _OLD_SHAPE_TAIL, _NEW_SHAPE_TAIL, "shape hard-link")
    source = _replace_once(source, _OLD_LOAD_STAT, _NEW_LOAD_STAT, "load hard-link")
    return source


def install_persistence_native_go_exact_object_integrity_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _native._GO_PERSIST_HELPERS = _harden(_native._GO_PERSIST_HELPERS)
    _codegen.CAPABILITY_RUNTIME = _harden(_codegen.CAPABILITY_RUNTIME)
    _INSTALLED = True
