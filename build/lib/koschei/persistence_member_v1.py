"""Current-runtime member bridge for exact-object persistence v1.

The base interpreter keeps capability member access fail-closed. Persistence opens
only the four edges required by its sealed authority graph:

    SystemCaps.persist
    PersistRoot.allow
    PersistCaps.load
    PersistCaps.commit

No generic narrowed-capability member access is enabled.
"""

from __future__ import annotations

from . import interpreter as _runtime
from .persistence_authority_v1 import PersistCaps, PersistRoot, SystemCaps

_INSTALLED = False
_ORIGINAL_MEMBER = None


def _member(self, receiver, name, location):
    if isinstance(receiver, SystemCaps) and name == "persist":
        return receiver.persist
    if isinstance(receiver, PersistRoot) and name == "allow":
        return _runtime._BoundMember(receiver, name, location)
    if isinstance(receiver, PersistCaps) and name in {"load", "commit"}:
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINAL_MEMBER(self, receiver, name, location)


def install_persistence_member_v1() -> None:
    global _INSTALLED, _ORIGINAL_MEMBER
    if _INSTALLED:
        return
    _ORIGINAL_MEMBER = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member
    _INSTALLED = True
