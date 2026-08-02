"""Runtime-only control signals for the v0.10 syntax nodes."""
from __future__ import annotations

from .ast_nodes import BreakStatement, ContinueStatement, LetStatement, MatchArm


class BreakSignal(Exception):
    """Leave the nearest Koschei loop in the tree-walking interpreter."""


class ContinueSignal(Exception):
    """Continue the nearest Koschei loop in the tree-walking interpreter."""


def install_node_references() -> None:
    """Compatibility hook retained for the isolated v0.10 installer."""
    return None


__all__ = [
    "BreakSignal",
    "BreakStatement",
    "ContinueSignal",
    "ContinueStatement",
    "LetStatement",
    "MatchArm",
    "install_node_references",
]
