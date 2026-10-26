"""Keep native PersistRoot narrowing semantically aligned with the interpreter.

A statically valid policy produces a PersistCaps token even if the parent directory
cannot currently be anchored. The token carries the open failure and `load` or
`commit` returns it as KS3424. Narrowing itself is not silently turned into a new
fallible-I/O surface in only one backend.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import persistence_native_go_v1 as _native

_INSTALLED = False

_OLD_STRUCT = '''type ksPersistCaps struct {
\tpolicy   ksPersistPolicy
\tparentFD int
\tname     string
}'''
_NEW_STRUCT = '''type ksPersistCaps struct {
\tpolicy    ksPersistPolicy
\tparentFD  int
\tname      string
\topenError string
}'''

_OLD_ALLOW = '''\tparentFD, name, openFailure := ksPersistOpenParent(canonical)
\tif openFailure != nil {
\t\treturn openFailure
\t}
\tcapability := &ksPersistCaps{
\t\tpolicy: ksPersistPolicy{
\t\t\tpath: canonical,
\t\t\tmaxBytes: maxBytes,
\t\t\tdeadlineMs: deadlineMs,
\t\t},
\t\tparentFD: parentFD,
\t\tname: name,
\t}'''
_NEW_ALLOW = '''\tparentFD, name, openFailure := ksPersistOpenParent(canonical)
\tcapability := &ksPersistCaps{
\t\tpolicy: ksPersistPolicy{
\t\t\tpath: canonical,
\t\t\tmaxBytes: maxBytes,
\t\t\tdeadlineMs: deadlineMs,
\t\t},
\t\tparentFD: parentFD,
\t\tname: name,
\t}
\tif openFailure != nil {
\t\tcapability.parentFD = -1
\t\tcapability.name = filepath.Base(canonical)
\t\tcapability.openError = openFailure.Message
\t}'''

_OLD_DUP = '''func ksPersistDupParent(capability *ksPersistCaps) (int, *KsError) {
\tif capability == nil || capability.parentFD < 0 {
\t\treturn -1, ksPersistIO("persistence parent descriptor is unavailable")
\t}'''
_NEW_DUP = '''func ksPersistDupParent(capability *ksPersistCaps) (int, *KsError) {
\tif capability == nil {
\t\treturn -1, ksPersistIO("persistence parent descriptor is unavailable")
\t}
\tif capability.parentFD < 0 {
\t\tif capability.openError != "" {
\t\t\treturn -1, &KsError{Message: capability.openError}
\t\t}
\t\treturn -1, ksPersistIO("persistence parent descriptor is unavailable")
\t}'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new in source:
        return source
    raise RuntimeError(
        f"Native persistence authority marker changed at {label}; fail-closed."
    )


def _align(source: str) -> str:
    source = _replace_once(source, _OLD_STRUCT, _NEW_STRUCT, "token state")
    source = _replace_once(source, _OLD_ALLOW, _NEW_ALLOW, "root narrowing")
    source = _replace_once(source, _OLD_DUP, _NEW_DUP, "operation failure")
    return source


def install_persistence_native_go_authority_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _native._GO_PERSIST_HELPERS = _align(_native._GO_PERSIST_HELPERS)
    _codegen.CAPABILITY_RUNTIME = _align(_codegen.CAPABILITY_RUNTIME)
    _INSTALLED = True
