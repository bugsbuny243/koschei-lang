"""Native Koschei sigil AST surface v1.

This module extends the existing Program without replacing the legacy/base AST.
The first native surface is intentionally small: a sigil root plus a canonical
subject. Deeper clauses will be added only when they have typed/MIR meaning.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import Program, SourceLocation


CANONICAL_SIGILS = frozenset({"ka", "vor", "shi", "thal", "nur"})


@dataclass(frozen=True, slots=True)
class SigilDeclaration:
    sigil: str
    subject: str
    location: SourceLocation

    def __post_init__(self) -> None:
        if self.sigil not in CANONICAL_SIGILS:
            raise ValueError(f"unknown Koschei sigil: {self.sigil}")
        if not self.subject:
            raise ValueError("Koschei sigil subject cannot be empty")


@dataclass(frozen=True, slots=True)
class NativeProgram(Program):
    """Program plus native Koschei semantic-root declarations."""

    sigils: tuple[SigilDeclaration, ...] = ()
