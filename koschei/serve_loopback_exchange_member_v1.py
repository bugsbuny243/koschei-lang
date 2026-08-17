"""Current-runtime member bridge for the one-shot Serve exchange.

Serve Authority v1 deliberately seals the interpreter capability-member boundary:
SystemCaps exposes only ``serve`` and ServeRoot exposes only ``allow``.  The
exchange slice extends that boundary by exactly one operation, ``ServeCaps.exchange``.
No generic narrowed-capability member access is enabled and ``listen`` remains
fail-closed.
"""

from __future__ import annotations

from . import interpreter as _runtime
from .serve_authority_v1 import ServeCaps

_INSTALLED = False
_ORIGINAL_MEMBER = None


def _member(self, receiver, name, location):
    if isinstance(receiver, ServeCaps) and name == "exchange":
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINAL_MEMBER(self, receiver, name, location)


def install_serve_loopback_exchange_member_v1() -> None:
    global _INSTALLED, _ORIGINAL_MEMBER
    if _INSTALLED:
        return
    _ORIGINAL_MEMBER = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member
    _INSTALLED = True
