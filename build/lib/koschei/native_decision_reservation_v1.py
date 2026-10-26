"""Tighten native decision identities against borrowed control vocabulary."""

from __future__ import annotations

from . import native_decision_realities_v1 as _decision
from .originality_contract_v1 import BORROWED_KEYWORD_BLOCKLIST_V1


_INSTALLED = False
_ORIGINAL_DECISION_NAME = _decision._decision_name


def _reserved_decision_name(token: str, *, line: int) -> str:
    if token in BORROWED_KEYWORD_BLOCKLIST_V1:
        _decision._fail(
            "KD1004",
            f"{token!r} is reserved borrowed vocabulary and cannot be a decision witness identity",
            line,
            1,
        )
    return _ORIGINAL_DECISION_NAME(token, line=line)


def install_native_decision_reservation_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _decision._decision_name = _reserved_decision_name
    _INSTALLED = True
