"""Native AST nodes for the first Koschei Universe source surface.

These nodes are intentionally small: they establish a real parsed representation
for ka/vor/shi/thal/nur without pretending that the legacy function-oriented AST
already owns Universe semantics.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import SourceLocation


CANONICAL_SIGILS = frozenset({"ka", "vor", "shi", "thal", "nur"})


@dataclass(frozen=True, slots=True)
class NativeSigilDeclaration:
    sigil: str
    subject: str
    location: SourceLocation

    def __post_init__(self) -> None:
        if self.sigil not in CANONICAL_SIGILS:
            raise ValueError(f"unknown canonical Koschei sigil: {self.sigil}")
        if not self.subject:
            raise ValueError("native sigil declaration requires a subject")


@dataclass(frozen=True, slots=True)
class NativeSigilProgram:
    declarations: tuple[NativeSigilDeclaration, ...]

    def __post_init__(self) -> None:
        if not self.declarations:
            raise ValueError("native sigil program requires at least one declaration")

    @property
    def sigils(self) -> tuple[str, ...]:
        return tuple(item.sigil for item in self.declarations)
