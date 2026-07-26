"""Koschei (.ks) — capability-secure programming language."""

from __future__ import annotations

__version__ = "0.9.0"

from .cli import main
from .runtime_alignment import install_runtime_alignment

install_runtime_alignment()

__all__ = ["main"]
